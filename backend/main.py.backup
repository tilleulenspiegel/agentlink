"""
AgentLink - Agent State Protocol
FastAPI Backend
"""
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from uuid import uuid4
import uvicorn

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
# IN-MEMORY STORE (PostgreSQL später)
# ============================================================================

states_db: dict[str, AgentState] = {}


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
async def health():
    return {
        "status": "healthy",
        "states_count": len(states_db),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/states", response_model=AgentState)
async def create_state(state: AgentState):
    """Store a new agent state."""
    states_db[state.id] = state
    # TODO: Persist to PostgreSQL
    # TODO: Broadcast via Redis Pub/Sub
    # TODO: Index in ChromaDB
    return state


@app.get("/states/{state_id}", response_model=AgentState)
async def get_state(state_id: str):
    """Retrieve an agent state by ID."""
    if state_id not in states_db:
        raise HTTPException(status_code=404, detail="State not found")
    return states_db[state_id]


@app.get("/states", response_model=List[AgentState])
async def list_states(
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
):
    """List states with optional filters."""
    results = list(states_db.values())
    
    if agent_id:
        results = [s for s in results if s.agent_id == agent_id]
    
    if status:
        results = [s for s in results if s.task.status == status]
    
    return results[:limit]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time state updates."""
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
