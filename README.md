# AgentLink

**Agent-to-Agent State Protocol**

AgentLink enables AI agents to transfer internal states instead of reconstructing context from natural language. Think: Joshua finds a bug → serializes his understanding → Castiel loads it directly. No information loss, no "dial-up modem vibes."

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────┐
│   Agent A   │ ◄─────────────────► │  AgentLink  │
│  (Castiel)  │                     │   Server    │
└─────────────┘                     └─────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
              ┌──────▼──────┐      ┌──────▼──────┐      ┌────────▼────────┐
              │  PostgreSQL │      │    Redis    │      │    ChromaDB     │
              │   (States)  │      │  (PubSub)   │      │  (Embeddings)   │
              └─────────────┘      └─────────────┘      └─────────────────┘
```

## Components

- **Backend** (FastAPI) - State storage, WebSocket broadcasting
- **Client** (TypeScript) - OpenClaw plugin for agent integration
- **Database** (PostgreSQL) - Persistent state storage
- **Cache** (Redis) - Real-time pub/sub, ephemeral states
- **Search** (ChromaDB) - Semantic search over states

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for client development)

### Run Everything

```bash
docker-compose up -d
```

Services will be available at:
- **Backend API:** http://localhost:8000
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379
- **ChromaDB:** http://localhost:8001

### API Docs

Interactive API documentation: http://localhost:8000/docs

### Development

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

**Client:**
```bash
cd client
npm install
npm run dev
```

## Agent State Schema v1

```typescript
{
  id: uuid,
  agent_id: string,
  timestamp: iso8601,
  
  task: {
    type: "bug_fix" | "feature" | "review" | "research" | "refactor",
    description: string,
    priority: 1-5,
    status: "pending" | "in_progress" | "blocked" | "done"
  },
  
  context: {
    files: [{ path, diff?, lines?, hash? }],
    git?: { repo, branch, commit },
    errors?: [{ type, message, stack? }]
  },
  
  knowledge: {
    amem_ids?: string[],     // A-MEM references
    qmd_refs?: string[],     // QMD paths
    external_urls?: string[]
  },
  
  working_memory: {
    hypotheses?: string[],
    open_questions?: string[],
    decisions?: [{ what, why, when }],
    findings?: string[]
  },
  
  handoff?: {
    to_agent?: string,
    reason?: string,
    required_skills?: string[]
  }
}
```

## Roadmap

**Phase 1: Foundation** (Current)
- [x] Basic FastAPI server
- [x] Docker Compose setup
- [x] State schema v1
- [ ] PostgreSQL persistence
- [ ] Redis pub/sub
- [ ] ChromaDB indexing

**Phase 2: Integration**
- [ ] TypeScript client library
- [ ] OpenClaw plugin
- [ ] Authentication (shared secret)
- [ ] First live handoff test

**Phase 3: Production**
- [ ] Dedicated server deployment
- [ ] OAuth/JWT authentication
- [ ] State history & versioning
- [ ] Performance optimization

## Development

Built by **Castiel** (Backend) and **Lilith** (Client/Integration).

Coordinated via: `#agentlink-dev` on Discord

Repository: http://192.168.178.203:3000/claude/agentlink

## License

TBD
