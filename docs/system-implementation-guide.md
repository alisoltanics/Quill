# System Architecture Guide

> **Architecture Guide**

This document is written from the ground up in simple language so that a beginner developer can understand what parts this system is built from, what each part does, and where data flows.

> **ℹ️ What is this document about?**
> This file explains the architecture, not the fine-grained coding details. It mainly answers which service does what and why this path was chosen.

| **6** | **2** | **1** |
|-------|-------|-------|
| Core services in the architecture | Separate databases for auth and documents | Single source of truth for final document state |

---

## Table of Contents

1. [Project Goal](#1-project-goal)
2. [System Overview](#2-system-overview)
3. [Microservice Principles](#3-microservice-principles-we-follow)
4. [Services and Responsibilities](#4-services-and-responsibilities)
5. [Databases](#5-databases)
6. [Document Data Model](#6-document-data-model)
7. [Authentication Flow](#7-authentication-flow)
8. [Opening a Document Flow](#8-opening-a-document-flow)
9. [Edit and Sync Flow](#9-edit-and-sync-flow)
10. [Online Users (Presence)](#10-online-users-presence)
11. [Remote Cursors](#11-remote-cursors)
12. [Audit Service and Kafka](#12-audit-service-and-kafka)
13. [Export Flow](#13-export-flow)
14. [Monitoring and Observability](#14-monitoring-and-observability)
15. [Current Limitations](#15-current-limitations)
16. [System Design Concepts for Practice and Learning](#16-system-design-concepts-for-practice-and-learning)
17. [Final Summary](#17-final-summary)

---

## 1) Project Goal

This project is a simple system for real-time collaborative document editing. Multiple users can work on a single document and see each other's changes.

> **⚠️ This project is built for learning only**
> The goal of this project is not to produce a ready-to-deploy product. The goal is to deeply understand microservice architecture concepts, system design, AI, and modern software engineering. All design decisions were made with the purpose of learning and better understanding architectural patterns.

### Topics you will learn in this project

- **Microservices Architecture**: How to split a large system into small, independent services, each with a clear responsibility.
- **System Design**: Learning design patterns for distributed systems, including CQRS, Event Sourcing, and Event-Driven Architecture.
- **Real-time Collaboration**: Understanding CRDT and OT patterns for multi-user concurrent document editing.
- **WebSocket and Real-time Communication**: Implementing bidirectional communication between client and server using WebSocket.
- **Authentication & Security**: Implementing JWT, refresh tokens, and modern authentication models.
- **Redis Pub/Sub Messaging**: Using Redis for inter-service communication and state coordination in distributed systems.
- **Event Streaming with Kafka**: Using Kafka for asynchronous events and service decoupling.
- **Observability and Monitoring**: Using Prometheus, Grafana, and Jaeger for system monitoring.
- **Testing**: Writing unit, integration, and end-to-end tests for different services.
- **DevOps and Docker**: Containerizing services and orchestrating them with Docker Compose.

In simple terms: here we will understand what each part does and how these parts together maintain a shared document.

> **✅ Educational Goal of the Project**
> Learning microservice architecture, WebSocket, Redis, JWT authentication, document storage in a separate service, Kafka, monitoring, and professional testing.

---

## 2) System Overview

To put it very simply, this project consists of several small programs, each performing a specific task.

Here, the Frontend is what the user sees in the browser, the Gateway is like the main gate, the Document Service is like a central notebook, and PostgreSQL is like a storage drawer.

```
Frontend ↔ Gateway ↔ Document Service ↔ PostgreSQL
```

```
Frontend ↔ Auth Service ↔ Auth PostgreSQL
```

```
Document Service → Redis → Gateway → Clients
```

So an important point is that the frontend does not communicate directly with all services. Most requests go through the Gateway.

> **ℹ️ Further Simple Explanation**
> The Gateway is the intermediary. If you want to view a document or verify a token, you tell the Gateway first, and then the Gateway forwards the message to the correct service.

---

## 3) Microservice Principles We Follow

| Principle | How we applied it |
|-----------|-------------------|
| **Single Responsibility** | Each service does one thing: Auth (login), Document (CRUD), Audit (logging), Export (PDF/HTML) |
| **Decentralized Data** | Each service owns its own database: `postgres-auth`, `postgres`, `audit-postgres` |
| **API Gateway** | Gateway is the single entry point — handles WebSocket + proxies REST |
| **Event-Driven** | Document service publishes to Kafka → Audit service consumes asynchronously |
| **Independent Deployment** | Each service has its own `Dockerfile` |
| **Observability** | Prometheus metrics, Jaeger tracing, structured logging |
| **Resilience** | Circuit breaker on downstream calls to prevent cascading failures |
| **Loose Coupling** | Services communicate only via HTTP, Redis, or Kafka — no shared DB |

---

## 4) Services and Responsibilities

| Service | Port | Main Job |
|---------|------|----------|
| frontend | `3000` | Display UI, open documents, edit documents, send user requests |
| gateway | `8080` | Main entry point for the frontend, WebSocket, JWT verification, and proxying some APIs |
| document-service | `8000` | Create, read, update, and delete documents and folders. Also stores `content` and `yjs_state` |
| auth-service | `8002` | Registration, login, refresh tokens, and user identification |
| export-service | `8001` | Convert documents to `html`, `markdown`, and `txt` |
| audit-service | `8003` | Consume `document.events` from Kafka and store document activity history |
| redis | `6379` | Message broadcasting between services |

> **ℹ️ Why are the services separated?**
> Because each service has a clear responsibility. This makes the system easier to understand and keeps changes to one part isolated from the others.

---

## 5) Databases

In the current state, the authentication service and the document service use two separate databases.

- **document database**: For documents, folders, and document versions
- **auth database**: For users of the authentication service

> **✅ Why is this separation important?**
> Because user data and document data are two different responsibilities. Keeping them separate makes the architecture cleaner and easier to maintain in the future.

---

## 6) Document Data Model

Each document has several important fields:

- `title`: The document title
- `content`: A simpler version of the content for display and fallback
- `yjs_state`: The collaborative version of the document for Yjs

In simple terms: `title` is like the document name, `content` is like plain text, and `yjs_state` is like a map that helps multiple people coordinate changes in real-time.

> **ℹ️ Why is Yjs/CRDT implemented?**
> Because when multiple people work on a document simultaneously, there must be a way to combine everyone's changes without corrupting the content. Yjs uses CRDT to make this coordination simpler and more reliable.
>
> In very simple terms: Yjs takes updates and "merges" them so that all users eventually see a coordinated text.

> **ℹ️ Why do we have both content and yjs_state?**
> Because `yjs_state` is needed for real-time collaboration, but for some simple displays or error conditions, having `content` helps prevent showing an empty document.

Each time a document is saved, a new version is also recorded in `DocumentVersion`.

---

## 7) Authentication Flow

User login is handled with JWT.

1. The user logs in or registers in the frontend.
2. The frontend sends a request to `auth-service`.
3. If the credentials are correct, two tokens are returned: `access_token` and `refresh_token`.
4. The frontend uses the access token for API and WebSocket requests.

### What happens when the access token expires?

1. If a request receives a `401`, the frontend attempts to get a new access token using the `refresh_token`.
2. If the refresh succeeds, the page reloads and comes back up with the new token.
3. If the refresh fails, the user is sent to the login page.

> **⚠️ Simple note**
> The `access_token` is for everyday use. The `refresh_token` is only used to get a new access token.

---

## 8) Opening a Document Flow

When a user clicks on a document or refreshes the page with a document URL, the following path is taken:

1. The frontend determines which document to open from the URL.
2. The frontend sends a `GET /api/documents/:id` request through the Gateway.
3. The Gateway forwards the request to the Document Service.
4. The Document Service reads the document data from the database.
5. The response is returned to the frontend.
6. If `yjs_state` is valid, it is applied to Yjs.
7. If not, `content` is used as a fallback.

This means the frontend does not fetch the document directly from the database; it first asks the Gateway, and then the Gateway tells the document service.

---

## 9) Edit and Sync Flow

This is the most important part of the project architecture.

> **⚠️ Current System Policy**
> Clients are only updated after changes have been saved in the document service database. This means there is no direct sync from client to other clients.

### Full Change Path

1. The user types in the editor.
2. Yjs in the frontend records the local change.
3. The frontend triggers autosave.
4. The frontend sends a `PATCH /api/documents/:id` request.
5. The Gateway forwards the request to the Document Service.
6. The Document Service saves the new content to PostgreSQL.
7. The Document Service also sends an event to Kafka so that independent services can do their work after this save.
8. If `yjs_state` exists, the Document Service publishes a `sync-state` message on Redis.
9. The Gateway, which is a subscriber to this channel, receives the message.
10. The Gateway broadcasts the same message to clients connected to that document.
11. Other clients apply that state.

```
Edit in Browser → PATCH /api/documents/:id → Document Service Save → Redis sync-state → Gateway Broadcast → Other Clients Apply
```

### Why was this approach chosen?

Because in this architecture, only data that has actually been saved in the database should reach other clients. This means the source of truth is always the Document Service and its database.

> **ℹ️ Simple reminder**
> This means if two people type at the same time, before everyone sees it, the system ensures that the changes have been recorded in the main document.

---

## 10) Online Users (Presence)

### Data Structure in Redis

A **Sorted Set** named `doc:{docId}:online` is used. Each member is a user's email, and the score is the last activity time (Unix timestamp).

```
Redis Key:   doc:42:online
Members:     ["ali@example.com", "sara@example.com"]
Scores:      [1693584000000, 1693584005000]
```

### Full Path

1. The user opens a WebSocket. The Gateway extracts the email from the JWT.
2. When the client sends a `join` message, the Gateway adds the user's email to the Sorted Set with `ZADD`.
3. The Gateway reads the full list of online users from Redis.
4. The Gateway publishes a `presence-update` message containing the full list of users on the Redis channel `gateway:events`.
5. All Gateway instances receive this message and broadcast it to connected clients.
6. The frontend receives and displays the list of online users.

```
Client Join → Gateway ZADD Redis → Gateway Get Full List → Publish presence-update → All Gateways Broadcast → Frontend Displays
```

### Automatic Cleanup

Each member has a TTL of 90 seconds. If a user disconnects (e.g., closes the browser), they are removed from the list after 90 seconds. Also, before reading the list, expired entries are cleaned up with `ZREMRANGEBYSCORE`.

### User Disconnect

1. When the WebSocket is closed, `readPump` detects it.
2. The Gateway removes the user's email from the Sorted Set with `ZREM`.
3. The updated list is published and broadcast to all clients.

> **ℹ️ Why a Sorted Set?**
> A Sorted Set allows us to quickly read the user list (`ZRANGE`), clean up old entries (`ZREMRANGEBYSCORE`), and have entries automatically expire if a Gateway crashes.

---

## 11) Remote Cursors

Each user can see other users' cursors live in the document. The cursor color is determined based on the user's email, and hovering over the cursor shows the user's email.

### Sending Cursor Position

1. Each time the user types or moves the cursor, the frontend sends a `cursor-update` message with the structure `{email, position}`.
2. The frontend throttles sending with a 30ms debounce to avoid sending excess messages.
3. The Gateway publishes the message on the Redis channel `gateway:events` so that all Gateway instances receive it.

### Receiving and Displaying

1. The frontend receives the `cursor-update` message from the Gateway.
2. The active cursors list (`remoteCursors`) is updated.
3. A ProseMirror plugin called `RemoteCursorsExtension` receives this list and creates a `Decoration.widget` at the appropriate position for each user.
4. The cursor color is generated from a hash of the user's email so that each user has a consistent color.

> **ℹ️ Why rebuild on every transaction?**
> The TipTap editor uses Yjs for synchronization. When a user types, Yjs creates a transaction that completely replaces the document content. If we used `DecorationSet.map`, cursor positions would become incorrect and cursors would disappear. That is why on every transaction, cursors are rebuilt based on the new document position.

### Overall Flow

```
User Types → Send cursor-update (30ms debounce) → Gateway Publish Redis → All Gateways Broadcast → Frontend Updates Plugin State → Rebuild Decorations
```

---

## 12) Audit Service and Kafka

After the Document Service saves changes to PostgreSQL, it publishes an independent event to Kafka.

This event is sent as a `document.updated` message and includes the document ID, user ID, version, timestamp, and client ID.

The Audit Service independently consumes this topic and records each event in the `audit_activity` table.

- Kafka topic: `document.events`
- Audit Service: `/api/documents/:id/activity`
- Activity storage via ORM with SQLAlchemy

> **ℹ️ Why Kafka?**
> Kafka allows downstream services to consume persistence events without a direct dependency on the Document Service.

---

## 13) Export Flow

For exports, the frontend does not go directly to the export-service. Like other APIs, it only calls the Gateway.

1. The user clicks Export in the frontend.
2. The frontend sends a `POST /api/export?format=...` request to the Gateway.
3. The Gateway proxies the request to the Export Service.
4. The Export Service converts the content to the desired format.
5. The output file is returned to the browser.

The Export Service only handles text conversion. The browser itself downloads the file and presents it to the user.

> **✅ Benefit of this approach**
> The frontend only knows one main entry point: the Gateway. This makes the architecture cleaner and simpler.

---

## 14) Monitoring and Observability

This section is for understanding whether the system is healthy, and if a problem occurs, where to look for the cause.

### Key Tools

- **Prometheus**: Collecting metrics
- **Grafana**: Displaying metrics on dashboards
- **Jaeger**: Viewing traces
- **redis-exporter**: Redis metrics
- **postgres-exporter**: PostgreSQL metrics
- **node-exporter**: Host system metrics

> **ℹ️ What do Grafana and Prometheus mean?**
> Prometheus is like an eye that collects numbers and service statuses. Grafana is like a display board that shows these numbers as charts and tables so you can quickly see what is wrong.

### Important Metrics

- Number of WebSocket connections in Gateway
- Number of messages received by Gateway
- Number of successful document saves
- Number of document save errors
- Number of Redis publishes from the Document Service

### Simple Monitoring Flow

1. Services produce metrics.
2. Prometheus collects these metrics.
3. Grafana displays them.
4. If tracing is enabled, traces go to Jaeger.

> **ℹ️ In very simple terms**
> Metrics tell us where we have problems. Traces help us understand exactly in which path the problem occurred.

---

## 15) Current Limitations

- Since sync only happens after save, real-time is slightly slower than direct broadcast.
- In some cases, fallback display depends on `content`.
- This is an educational project, so some security and production-level configurations are still kept simple.

---

## 16) System Design Concepts for Practice and Learning

This section covers key system design concepts implemented in this project for educational purposes. These patterns are essential for building reliable distributed systems.

### 16.1 Idempotency

**What is idempotency?**
Idempotency means that performing an operation multiple times has the same effect as performing it once. This is crucial in distributed systems where network issues can cause duplicate requests.

**Why is it important?**
- Prevents duplicate data creation when retries happen
- Ensures system consistency despite network failures
- Common in payment systems, API design, and distributed transactions

**How we implemented idempotency:**

1. **Client-side**: The frontend generates a unique idempotency key (UUID) for each folder creation request and sends it in the `Idempotency-Key` header.

2. **Server-side**: The Document Service extracts the key from the request header and uses Django's `get_or_create` with a partial unique constraint on `(user_id, idempotency_key)`.

3. **Database constraint**: A partial unique index ensures that only one folder can exist per user with a given idempotency key (NULL keys are excluded).

**Code flow:**
```python
# Frontend: generates unique key per operation
const key = crypto.randomUUID();
await authFetch('/folders', {
  method: 'POST',
  headers: { 'Idempotency-Key': key },
  body: JSON.stringify({ name: 'New Folder' })
});

# Backend: uses get_or_create with the key
folder, created = Folder.objects.get_or_create(
    user_id=uid,
    idempotency_key=key,
    defaults={"name": name},
)
# Returns 201 if created, 200 if replayed
```

**Key benefits demonstrated:**
- Prevents duplicate folders from network retries
- Different users can use the same key (scoped per user)
- Without key, operations are not idempotent (two creates = two folders)
- Oversized keys are rejected (max 255 characters)

**Testing idempotency:**
- First request with key: creates folder (201)
- Second request with same key: returns same folder (200)
- Different keys: create separate folders
- Same key, different user: creates separate folders (user scoping)

### 16.2 Circuit Breaker Pattern (Implemented)

#### The Problem

If the Document Service goes down, the Gateway keeps sending requests to it, wasting time and resources. Clients wait and get errors anyway.

#### The Solution

A circuit breaker acts like an electrical fuse. After seeing enough failures, it **stops sending requests** and immediately returns "service unavailable."

#### Three States

| State | What happens |
|-------|-------------|
| **Closed** (normal) | Requests go through. Failures are counted. |
| **Open** (broken) | Requests blocked immediately. Returns 503. No waiting. |
| **Half-Open** (testing) | After 10 seconds, one request is allowed through to test if service recovered. |

#### Default Settings

| Setting | Value | What it means |
|---------|-------|---------------|
| Fail threshold | 5 | Number of failures before circuit opens |
| Success threshold | 2 | Number of successes to close circuit again |
| Open timeout | 10s | How long to wait before testing again |

#### Where It Protects

- `/api/` → Document Service proxy
- `/api/export` → Export Service proxy

#### Example Scenario

1. Document service starts returning 500 errors
2. After 5 consecutive failures, the circuit opens
3. Gateway immediately returns 503 to clients (fast fail, no waiting)
4. After 10 seconds, the circuit goes half-open and allows one probe
5. If the probe succeeds (200 OK), the circuit closes and normal flow resumes

#### Prometheus Metrics

```promql
# State transitions per service
gateway_circuit_breaker_transitions_total{service="document-service", from="closed", to="open"}

# Requests rejected by circuit breaker
gateway_circuit_breaker_rejections_total{service="export-service"}
```

#### Files

- `services/gateway/circuit_breaker.go` — implementation
- `services/gateway/circuit_breaker_test.go` — 14 unit tests

### 16.3 CQRS (Implemented)

The document service uses **CQRS** — separating read and write operations into different modules.

#### The Problem

In a monolithic view, one function handles both reads and writes. This mixes concerns and makes it harder to scale reads independently.

#### The Solution

Split the document service into:
- **Commands** (`commands.py`) — write operations (create, update, delete)
- **Queries** (`queries.py`) — read operations (list, get, check access)

```
Commands (writes)                Queries (reads)
┌──────────────────┐            ┌──────────────────┐
│ create_folder()  │            │ list_folders()   │
│ update_folder()  │            │ get_folder()     │
│ delete_folder()  │            │ list_documents() │
│ create_document()│            │ get_document()   │
│ update_document()│            │ has_access()     │
│ delete_document()│            │ list_permissions()│
│ share_document() │            │ list_shared()    │
│ update_permission│            │ count_owners()   │
│ delete_permission│            └──────────────────┘
└──────────────────┘
         │                          │
         ▼                          ▼
   Write DB (postgres)        Read DB (same DB now,
                              can be replica later)
```

#### Benefits

| Benefit | Explanation |
|---------|-------------|
| **Read scaling** | Queries can hit read replicas without affecting writes |
| **Write optimization** | Commands focus on consistency, not read performance |
| **Clear boundaries** | Each module has a single responsibility |
| **Testability** | Commands and queries can be tested independently |
| **Future flexibility** | Easy to swap read DB for a cache or Elasticsearch |

#### Files

- `services/document_service/api/commands.py` — all write operations
- `services/document_service/api/queries.py` — all read operations
- `services/document_service/api/views.py` — HTTP layer that delegates to commands/queries

#### Example

Before CQRS (mixed):
```python
# One view does everything
def get(self, request, pk):
    doc = Document.objects.get(pk=pk)
    return JsonResponse(DocumentSerializer(doc).data)

def patch(self, request, pk):
    doc = Document.objects.get(pk=pk)
    doc.title = request.data["title"]
    doc.save()
    return JsonResponse(DocumentSerializer(doc).data)
```

After CQRS (separated):
```python
# views.py — thin HTTP layer
def get(self, request, pk):
    doc = queries.can_access_document(pk, _uid(request), _user_email(request))
    return JsonResponse(DocumentDetailSerializer(doc).data)

def patch(self, request, pk):
    doc = commands.update_document(doc, title=data["title"], user_id=uid)
    return JsonResponse(DocumentSerializer(doc).data)
```

### 16.4 Outbox Pattern (Implemented)

#### Why we implemented it

When a user edits a document, two things must happen:
1. Save the document to the database
2. Notify other services (Redis for real-time sync, Kafka for audit logging)

The problem: **what if step 2 fails?** The document is saved, but other services never find out. The database and message broker go out of sync.

Before the outbox pattern:
```
Save doc     → OK
Publish Redis → FAILS (network error)
Publish Kafka → FAILS (Kafka down)

Result: Document saved, but no one knows about it
```

#### How it works

Instead of publishing directly, we **write the event to a table in the same database transaction** as the document save. A background worker then reads and publishes.

```
Step 1: Save document + write event to outbox (same transaction)
┌─────────────────────────────────────────┐
│ BEGIN TRANSACTION                       │
│   INSERT INTO documents (...)           │  ← save document
│   INSERT INTO outbox_messages (...)     │  ← save event
│ COMMIT                                  │  ← both succeed or both fail
└─────────────────────────────────────────┘

Step 2: Background worker polls outbox every 5 seconds
┌─────────────────────────────────────────┐
│ SELECT * FROM outbox_messages           │
│ WHERE published = false                 │
└─────────────────────────────────────────┘

Step 3: Worker publishes to Kafka/Redis, then marks as published
┌─────────────────────────────────────────┐
│ UPDATE outbox_messages                  │
│ SET published = true                    │
│ WHERE id = ...                          │
└─────────────────────────────────────────┘
```

#### What happens if Redis fails

Redis publish happens after the transaction commits. If it fails, the event is lost (same as before).

#### What happens if Kafka fails

The event stays in the outbox table with `published = false`. The worker retries on the next poll. **No Kafka events are ever lost.**

```
Save doc + outbox  → OK
Worker tries Kafka → FAILS (Kafka down)
Worker tries again → FAILS
Worker tries again → OK (Kafka recovered)
Mark published     → done
```

#### How it's implemented

| File | What it does |
|------|-------------|
| `api/models.py` | `OutboxMessage` model — stores events |
| `api/commands.py` | Writes events to outbox in same transaction as doc save |
| `api/outbox.py` | Background processor — polls outbox, publishes to Kafka/Redis |
| `api/management/commands/run_outbox_processor.py` | Django command to start the worker |

**OutboxMessage model:**
```python
class OutboxMessage(models.Model):
    aggregate_type = models.CharField(max_length=64)  # "document"
    aggregate_id = models.IntegerField()              # document.pk
    event_type = models.CharField(max_length=64)      # "document.updated"
    payload = models.JSONField()                      # event data
    published = models.BooleanField(default=False)    # retry until true
    created_at = models.DateTimeField(auto_now_add=True)
```

**Command writes to outbox:**
```python
def update_document(doc, *, content=UNSET, ...):
    with transaction.atomic():
        doc.save()
        version = DocumentVersion.objects.create(...)
        # Write event to outbox in same transaction
        OutboxMessage.objects.create(
            aggregate_type="document",
            aggregate_id=doc.pk,
            event_type="document.updated",
            payload={"document_id": doc.pk, "version": version.pk},
        )
```

**Worker publishes:**
```python
def process_outbox(batch_size=10):
    messages = OutboxMessage.objects.filter(published=False)[:batch_size]
    for msg in messages:
        _publish_to_kafka(topic, payload)   # retry safe
        _publish_to_redis(payload)           # retry safe
        msg.published = True
        msg.save(update_fields=["published"])
```

#### Running the worker

The outbox processor starts automatically with the document-service. To run manually:

```bash
python manage.py run_outbox_processor --interval 5 --batch-size 10
```

| Flag | Default | What it does |
|------|---------|-------------|
| `--interval` | 5 | Seconds between polls |
| `--batch-size` | 10 | Max events per batch |

#### Guarantee

**At-least-once delivery** — events are retried until successfully published. No events are lost, even if Kafka or Redis is temporarily unavailable.

### 16.5 Other System Design Concepts (Future Practice)

While idempotency and circuit breaker are implemented, other important concepts can be added for further learning:

1. ~~**Circuit Breaker Pattern**~~ ✅ Implemented
2. **Bulkhead Pattern**: Isolate components to prevent failure propagation  
3. **Retry with Exponential Backoff**: Smart retry strategies for failed operations
4. **Event Sourcing**: Store state changes as a sequence of events
5. ~~**CQRS (Command Query Responsibility Segregation)**~~ ✅ Implemented
6. **Saga Pattern**: Manage distributed transactions across services
7. **Rate Limiting**: Control request rates to protect services
8. **Caching Strategies**: Implement caching for performance optimization
9. ~~**Transactional Outbox**~~ ✅ Implemented

> **✅ Learning Outcome**
> Understanding idempotency helps in designing reliable APIs and distributed systems where network reliability cannot be guaranteed.

---

## 17) Final Summary

If we want to describe the entire architecture in a few sentences:

- The frontend displays the user interface.
- The Gateway is the main entry point of the system.
- The Document Service is the source of truth for documents.
- The Auth Service is the source of truth for users and tokens.
- Redis is used as the canonical message broadcaster.
- Clients are only updated after changes are saved in the document database.
- Idempotency ensures reliable operations in distributed environments.

> **✅ One very important sentence**
> In this architecture, the final version of the document is always determined by the Document Service, not by the client itself.
