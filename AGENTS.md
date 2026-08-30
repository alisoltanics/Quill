# Project Context — READ THIS FIRST

## ⚠️ Purpose: Learning, not production

This project exists **only for practice and learning**. The goal is to deeply
understand system design, microservices architecture, and Go — not to ship a
polished product fast.

Because of this, always follow these rules in every suggestion, code review,
## Project Context — READ THIS FIRST

Purpose (learning, not production)

This repository is a learning playground to explore real-time collaboration
patterns and microservice design. Prioritize clarity and explicit patterns
over shortcuts.

Guidelines
- Prefer explicit, textbook patterns (dependency injection, clear boundaries).
- Explain the reasoning for design choices — not just the code.
- When multiple architectures are possible, list options and why one was
     chosen.
- Use idiomatic Go for the gateway (goroutines, channels, interfaces).

Project: Real-time Collaborative Document System

Short description
This is a simple Figma/Notion-like system split into services to practice
real-time collaboration: WebSocket gateway, document service, ephemeral
presence, and helper services.

Architecture (overview)
- WebSocket Gateway (Go): accepts many WebSocket clients and forwards events
     via Redis pub/sub so multiple gateway instances stay in sync.
- Document Service (Django + DRF): applies merge logic (OT/CRDT) and persists
     documents in PostgreSQL.
- Presence & Cursor: ephemeral state stored in Redis and broadcast by the
     gateway.

Tech stack
- Go — WebSocket gateway
- Django + DRF — document service and APIs
- Redis — pub/sub + ephemeral presence
- PostgreSQL — persistent document storage
- Docker Compose — local dev orchestration

Audience note
The maintainer is experienced with Django/DRF and learning Go; explain Go
idioms when suggesting changes.

Milestones (short)
- Scaffold repo, services, and docker-compose
- Basic WebSocket gateway that accepts connections and echoes messages
- Redis pub/sub across gateway instances
- Django Document Service with a `Document` model and REST endpoints
- Wire gateway → Redis → Document Service for persistence
- Presence/cursor broadcast
- Simple OT/CRDT merge logic for concurrent edits
- Dockerize and verify locally with `docker-compose up`

FastAPI service (design-only)

Purpose: a lightweight, stateless helper service for async tasks like
rendering previews, import/export, and receiving webhooks.

Why FastAPI: async support, Pydantic validation, automatic OpenAPI docs,
and good performance for I/O-bound tasks.

Suggested endpoints
- `GET /health` — health check
- `POST /render` — produce a preview from document content (async)
- `POST /webhook` — receive webhooks and publish messages to Redis
- `GET /documents/{id}/preview` — return a document preview

Integration patterns
- Keep the service stateless; integrate via Redis (pub/sub) or HTTP to the
     Document Service.
- For long jobs, push tasks to a queue/Redis and process with background
     workers.

Suggested layout
services/fastapi_service/
     - app/main.py (FastAPI app)
     - app/routers/
     - app/schemas.py (Pydantic models)
     - app/deps.py (dependencies, Redis client)
     - Dockerfile
     - requirements.txt

Note: this section is documentation-only. Do not implement unless instructed.
- Docker Compose: local environment for running services together

### Audience / Maintainer notes
- The maintainer has strong Django/DRF experience and is learning Go. When
     suggesting Go changes, prefer explanations of Go idioms and tradeoffs.

### Current milestones
- [ ] Scaffold repo structure (services, docker-compose, README)
- [ ] WebSocket Gateway (Go): accept connections and echo messages
- [ ] Redis pub/sub between gateway instances
- [ ] Document Service (Django): basic Document model and REST endpoints
- [ ] Wire gateway → Redis → Document Service for persistence
- [ ] Presence/cursor broadcast over WebSocket
- [ ] Basic OT/CRDT for concurrent text edits
- [ ] Dockerize everything and validate with `docker-compose up`
- [ ] (stretch) Add OpenTelemetry tracing across services

### FastAPI Service (Python / FastAPI)

Purpose: a lightweight, stateless service for async I/O-bound tasks and
quick endpoints (rendering/previews, import/export, webhooks, public
endpoints).

Why FastAPI:
- Native async support, Pydantic models for validation, automatic OpenAPI
     docs, and solid performance for I/O-bound workloads.

Suggested endpoints:
- `GET /health` — health check
- `POST /render` — generate a preview from document content (async)
- `POST /webhook` — receive webhooks and publish messages to Redis
- `GET /documents/{id}/preview` — return a document preview

Integration patterns:
- Keep the service stateless. Integrate via Redis (pub/sub) or via HTTP calls
     to the Document Service for persistence.
- Publish long-running work to a queue/Redis and handle it in background
     workers.

Suggested layout:
```
services/fastapi_service/
     app/main.py         # FastAPI application
     app/routers/*.py    # route modules
     app/schemas.py      # Pydantic models
     app/deps.py         # dependency wiring (Redis, clients)
     Dockerfile
     requirements.txt
```

Example dependencies (suggested): `fastapi`, `uvicorn[standard]`, `httpx`,
`aioredis`, `pydantic`.

Note: this section is design-only. Implement the service only if instructed.
