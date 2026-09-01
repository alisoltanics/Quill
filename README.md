# Real-time Collaborative Document System

## Project Overview
This repository is a learning project that demonstrates a simple,
microservice-based real-time collaborative editor. The goal is to show how
components interact (WebSocket gateways, Redis, a document service, and
helper services) and to provide a clear implementation path.

## Components and responsibilities

- WebSocket Gateway (Go)
  - Accepts client WebSocket connections.
  - Broadcasts incoming edits to local clients for a responsive experience.
  - Publishes edits to Redis so all gateway instances stay in sync.
  - Forwards persistence requests to the Document Service.

- Document Service (Django + DRF)
  - Receives persistence requests, merges concurrent edits (OT/CRDT), and
    stores documents in PostgreSQL.
  - Publishes persistence events after successful saves.
  - Emits `document.updated` events to Kafka so downstream consumers can
    react independently.

- Audit Service (FastAPI)
  - Consumes `document.events` from Kafka.
  - Persists document activity into PostgreSQL and exposes an audit API.

- Redis
  - Central pub/sub bus for cross-instance events.
  - Stores ephemeral state like presence and cursor positions.

- PostgreSQL
  - Stores final document state and change history.

- FastAPI (helper service)
  - Stateless endpoints for tasks like rendering previews, import/export,
    and receiving webhooks. Pushes heavy work to background workers.

- Background Workers
  - Consume task queues or Redis streams to run long-running jobs (render,
    export) and publish results.

## Simple system flow (plain steps)

1. Client connects to a WebSocket Gateway.
2. User edits a document; the client sends a small "delta" to the gateway.
3. Gateway shows the delta to local clients immediately and publishes the
   delta to Redis so other gateway instances receive it.
4. Gateway sends a persistence request to the Document Service.
5. Document Service merges the change, stores it in PostgreSQL, and emits a
   persistence event to Redis.
6. Gateways receive the persistence event and broadcast the final update to
   their connected clients.
7. FastAPI/workers handle additional work (previews, exports) and publish
   results back to Redis; gateways broadcast as needed.

## Implementation plan (recommended order)
1. Scaffold the repository and add a `docker-compose.yml` for Redis and
   PostgreSQL.
2. Implement a minimal WebSocket gateway in Go that accepts connections and
   echoes messages.
3. Add Redis pub/sub and validate cross-instance message delivery.
4. Scaffold a Django Document Service with a `Document` model and REST API.
5. Wire gateway → Redis → Document Service for persistence.
6. Add presence/cursor tracking in Redis and broadcast to clients.
7. Implement a simple OT/CRDT merge strategy.
8. Add a FastAPI helper service and background workers for previews/exports.
9. Dockerize and test with `docker-compose up`.

## Where to look
- Architectural and design notes: [AGENTS.md](AGENTS.md)

## Next steps
- I can scaffold `services/fastapi_service/` or create minimal gateway/Django
  stubs. Which service should I scaffold first?


