"""
AgentLink - Agent State Protocol
FastAPI Backend with Redis Pub/Sub
"""
from fastapi import FastAPI, WebSocket, HTTPException, Depends, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Set
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
import uvicorn
import asyncio
import json
import logging
import os
from redis.asyncio import Redis

from database import get_db, init_db, AgentStateDB

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client: Optional[Redis] = None
pubsub = None

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections and subscriptions"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "all": set(),  # Clients subscribed to all states
        }
    
    async def connect(self, websocket: WebSocket, channel: str = "all"):
        """Accept WebSocket connection and subscribe to channel"""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        logger.info(f"Client connected to channel: {channel}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket from all subscriptions"""
        for channel_set in self.active_connections.values():
            if websocket in channel_set:
                channel_set.remove(websocket)
        logger.info("Client disconnected")
    
    async def broadcast(self, message: dict, channel: str = "all"):
        """Broadcast message to all clients subscribed to channel"""
        message_json = json.dumps(message)
        
        # Broadcast to "all" channel
        if channel == "all":
            dead_connections = set()
            for ws in self.active_connections.get("all", set()):
                try:
                    await ws.send_text(message_json)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")
                    dead_connections.add(ws)
            
            # Cleanup dead connections
            for ws in dead_connections:
                self.disconnect(ws)
        
        # Broadcast to specific agent channel
        if channel.startswith("agent:"):
            dead_connections = set()
            for ws in self.active_connections.get(channel, set()):
                try:
                    await ws.send_text(message_json)
                except Exception as e:
                    logger.error(f"Error broadcasting to {channel}: {e}")
                    dead_connections.add(ws)
            
            # Cleanup dead connections
            for ws in dead_connections:
                self.disconnect(ws)

manager = ConnectionManager()

app = FastAPI(
    title="AgentLink API",
    description="Agent-to-Agent State Protocol with Redis Pub/Sub",
    version="0.3.0"
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# REDIS PUB/SUB
# ============================================================================

async def redis_listener():
    """Background task listening to Redis Pub/Sub"""
    global redis_client, pubsub
    
    try:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        
        # Subscribe to broadcast channel
        await pubsub.subscribe("agentlink:states")
        logger.info("Redis listener started - subscribed to agentlink:states")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    
                    # Broadcast to WebSocket clients
                    await manager.broadcast(data, channel="all")
                    
                    # Also broadcast to agent-specific channel if applicable
                    if "from_agent" in data:
                        agent_channel = f"agent:{data['from_agent']}"
                        await manager.broadcast(data, channel=agent_channel)
                    
                    logger.info(f"Broadcasted message: {data.get('type', 'unknown')}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from Redis: {e}")
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
    
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
        # Exponential backoff reconnect
        await asyncio.sleep(5)
        logger.info("Attempting to reconnect...")
        asyncio.create_task(redis_listener())


async def publish_to_redis(channel: str, message: dict):
    """Publish message to Redis channel"""
    global redis_client
    
    if not redis_client:
        logger.warning("Redis client not initialized - skipping publish")
        return
    
    try:
        message_json = json.dumps(message)
        await redis_client.publish(channel, message_json)
        logger.info(f"Published to {channel}: {message.get('type', 'unknown')}")
    except Exception as e:
        logger.error(f"Error publishing to Redis: {e}")


# ============================================================================
# SCHEMA - Agent State v1
# ============================================================================

class FileContext(BaseModel):
    path: str
    diff: Optional[str] = None
    lines: Optional[tuple[int, int]] = None
    hash: Optional[str] = None  # git blob hash


class GitContext(BaseModel):
    repo: str
    branch: str
    commit: str


class ErrorContext(BaseModel):
    type: str
    message: str
    stack: Optional[str] = None


class Context(BaseModel):
    files: List[FileContext] = []
    git: Optional[GitContext] = None
    errors: List[ErrorContext] = []


class Knowledge(BaseModel):
    amem_ids: List[str] = []
    qmd_refs: List[str] = []
    external_urls: List[str] = []


class Decision(BaseModel):
    what: str
    why: str
    when: datetime


class WorkingMemory(BaseModel):
    hypotheses: List[str] = []
    open_questions: List[str] = []
    decisions: List[Decision] = []
    findings: List[str] = []


class Task(BaseModel):
    type: Literal["bug_fix", "feature", "review", "research", "refactor"]
    description: str
    priority: int = Field(ge=1, le=5)
    status: Literal["pending", "in_progress", "blocked", "done"] = "pending"


class Handoff(BaseModel):
    to_agent: Optional[str] = None
    reason: Optional[str] = None
    required_skills: List[str] = []


class AgentState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    task: Task
    context: Context
    knowledge: Knowledge = Knowledge()
    working_memory: WorkingMemory = WorkingMemory()
    handoff: Optional[Handoff] = None


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def pydantic_to_db(state: AgentState) -> AgentStateDB:
    """Convert Pydantic model to SQLAlchemy model"""
    return AgentStateDB(
        id=state.id,
        agent_id=state.agent_id,
        timestamp=state.timestamp,
        task=state.task.model_dump(mode="json"),
        context=state.context.model_dump(mode="json"),
        knowledge=state.knowledge.model_dump(mode="json"),
        working_memory=state.working_memory.model_dump(mode="json"),
        handoff=state.handoff.model_dump(mode="json") if state.handoff else None
    )


def db_to_pydantic(db_state: AgentStateDB) -> AgentState:
    """Convert SQLAlchemy model to Pydantic model"""
    return AgentState(
        id=db_state.id,
        agent_id=db_state.agent_id,
        timestamp=db_state.timestamp,
        task=Task(**db_state.task),
        context=Context(**db_state.context),
        knowledge=Knowledge(**db_state.knowledge),
        working_memory=WorkingMemory(**db_state.working_memory),
        handoff=Handoff(**db_state.handoff) if db_state.handoff else None
    )


# ============================================================================
# STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database and Redis listener on startup"""
    init_db()
    asyncio.create_task(redis_listener())
    logger.info("AgentLink backend started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup Redis connections on shutdown"""
    global redis_client, pubsub
    
    if pubsub:
        await pubsub.close()
    if redis_client:
        await redis_client.close()
    logger.info("AgentLink backend shutdown")


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "AgentLink",
        "version": "0.3.0",
        "status": "online",
        "features": ["PostgreSQL", "Redis Pub/Sub", "WebSocket"],
        "endpoints": {
            "health": "/health",
            "states": "/states",
            "websocket": "/ws"
        }
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check with state count and Redis status"""
    count = db.query(AgentStateDB).count()
    
    redis_status = "disconnected"
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "error"
    
    return {
        "status": "healthy",
        "states_count": count,
        "redis": redis_status,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/states", response_model=AgentState)
async def create_state(state: AgentState, db: Session = Depends(get_db)):
    """Store a new agent state and broadcast via Redis"""
    # Save to PostgreSQL
    db_state = pydantic_to_db(state)
    db.add(db_state)
    db.commit()
    db.refresh(db_state)
    
    # Broadcast via Redis Pub/Sub
    event_message = {
        "type": "state_created",
        "state_id": state.id,
        "from_agent": state.agent_id,
        "timestamp": state.timestamp.isoformat(),
        "task_type": state.task.type,
        "task_status": state.task.status,
    }
    
    await publish_to_redis("agentlink:states", event_message)
    
    # If handoff, also publish to target agent channel
    if state.handoff and state.handoff.to_agent:
        handoff_message = {
            "type": "handoff_received",
            "state_id": state.id,
            "from_agent": state.agent_id,
            "to_agent": state.handoff.to_agent,
            "reason": state.handoff.reason,
            "timestamp": state.timestamp.isoformat(),
        }
        await publish_to_redis(f"agentlink:agent:{state.handoff.to_agent}", handoff_message)
    
    return db_to_pydantic(db_state)


@app.get("/states/{state_id}", response_model=AgentState)
async def get_state(state_id: str, db: Session = Depends(get_db)):
    """Retrieve an agent state by ID from PostgreSQL"""
    db_state = db.query(AgentStateDB).filter(AgentStateDB.id == state_id).first()
    if not db_state:
        raise HTTPException(status_code=404, detail="State not found")
    return db_to_pydantic(db_state)


@app.get("/states", response_model=List[AgentState])
async def list_states(
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List states with optional filters from PostgreSQL"""
    query = db.query(AgentStateDB)
    
    if agent_id:
        query = query.filter(AgentStateDB.agent_id == agent_id)
    
    results = query.order_by(AgentStateDB.timestamp.desc()).limit(limit).all()
    return [db_to_pydantic(s) for s in results]


@app.delete('/states/{state_id}')
async def delete_state(state_id: str, db: Session = Depends(get_db)):
    """Delete an agent state by ID"""
    db_state = db.query(AgentStateDB).filter(AgentStateDB.id == state_id).first()
    if not db_state:
        raise HTTPException(status_code=404, detail='State not found')
    db.delete(db_state)
    db.commit()
    return {'deleted': state_id}


# ============================================================================
# WEBSOCKET - Real-time Updates
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time state updates"""
    current_channel = "all"
    
    try:
        await manager.connect(websocket, channel=current_channel)
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "channel": current_channel,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        while True:
            # Receive subscription commands from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                action = message.get("action")
                
                if action == "subscribe":
                    new_channel = message.get("channel", "all")
                    
                    # Unsubscribe from current
                    if current_channel in manager.active_connections:
                        manager.active_connections[current_channel].discard(websocket)
                    
                    # Subscribe to new
                    if new_channel.startswith("agent:") or new_channel == "all":
                        current_channel = new_channel
                        if current_channel not in manager.active_connections:
                            manager.active_connections[current_channel] = set()
                        manager.active_connections[current_channel].add(websocket)
                        
                        await websocket.send_json({
                            "type": "subscribed",
                            "channel": current_channel,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                
                elif action == "unsubscribe":
                    manager.disconnect(websocket)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    break
                
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown action: {action}"
                    })
            
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected from channel: {current_channel}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
