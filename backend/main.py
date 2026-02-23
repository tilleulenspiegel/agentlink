"""
AgentLink - Agent State Protocol
FastAPI Backend
"""
from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
import uvicorn

from database import get_db, init_db, AgentStateDB

app = FastAPI(
    title="AgentLink API",
    description="Agent-to-Agent State Protocol",
    version="0.1.0"
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
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "AgentLink",
        "version": "0.1.0",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "states": "/states",
            "websocket": "/ws"
        }
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check with state count from database"""
    count = db.query(AgentStateDB).count()
    return {
        "status": "healthy",
        "states_count": count,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/states", response_model=AgentState)
async def create_state(state: AgentState, db: Session = Depends(get_db)):
    """Store a new agent state in PostgreSQL"""
    db_state = pydantic_to_db(state)
    db.add(db_state)
    db.commit()
    db.refresh(db_state)
    # TODO: Broadcast via Redis Pub/Sub
    # TODO: Index in ChromaDB
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
    
    # TODO: Filter by status (need to query JSON field)
    
    results = query.order_by(AgentStateDB.timestamp.desc()).limit(limit).all()
    return [db_to_pydantic(s) for s in results]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time state updates"""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            # TODO: Handle subscriptions
            # TODO: Redis Pub/Sub integration
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


@app.delete('/states/{state_id}')
async def delete_state(state_id: str, db: Session = Depends(get_db)):
    """Delete an agent state by ID"""
    db_state = db.query(AgentStateDB).filter(AgentStateDB.id == state_id).first()
    if not db_state:
        raise HTTPException(status_code=404, detail='State not found')
    db.delete(db_state)
    db.commit()
    return {'deleted': state_id}
