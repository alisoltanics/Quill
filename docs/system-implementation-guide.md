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
3. [Services and Responsibilities](#3-services-and-responsibilities)
4. [Databases](#4-databases)
5. [Document Data Model](#5-document-data-model)
6. [Authentication Flow](#6-authentication-flow)
7. [Opening a Document Flow](#7-opening-a-document-flow)
8. [Edit and Sync Flow](#8-edit-and-sync-flow)
9. [Online Users (Presence)](#9-online-users-presence)
10. [Remote Cursors](#10-remote-cursors)
11. [Audit Service and Kafka](#11-audit-service-and-kafka)
12. [Export Flow](#12-export-flow)
13. [Monitoring and Observability](#13-monitoring-and-observability)
14. [Current Limitations](#14-current-limitations)
15. [Final Summary](#15-final-summary)

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

## 3) Services and Responsibilities

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

## 4) Databases

In the current state, the authentication service and the document service use two separate databases.

- **document database**: For documents, folders, and document versions
- **auth database**: For users of the authentication service

> **✅ Why is this separation important?**
> Because user data and document data are two different responsibilities. Keeping them separate makes the architecture cleaner and easier to maintain in the future.

---

## 5) Document Data Model

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

## 6) Authentication Flow

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

## 7) Opening a Document Flow

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

## 8) Edit and Sync Flow

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

## 9) Online Users (Presence)

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

## 10) Remote Cursors

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

## 11) Audit Service and Kafka

After the Document Service saves changes to PostgreSQL, it publishes an independent event to Kafka.

This event is sent as a `document.updated` message and includes the document ID, user ID, version, timestamp, and client ID.

The Audit Service independently consumes this topic and records each event in the `audit_activity` table.

- Kafka topic: `document.events`
- Audit Service: `/api/documents/:id/activity`
- Activity storage via ORM with SQLAlchemy

> **ℹ️ Why Kafka?**
> Kafka allows downstream services to consume persistence events without a direct dependency on the Document Service.

---

## 12) Export Flow

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

## 13) Monitoring and Observability

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

## 14) Current Limitations

- Since sync only happens after save, real-time is slightly slower than direct broadcast.
- In some cases, fallback display depends on `content`.
- This is an educational project, so some security and production-level configurations are still kept simple.

---

## 15) Final Summary

If we want to describe the entire architecture in a few sentences:

- The frontend displays the user interface.
- The Gateway is the main entry point of the system.
- The Document Service is the source of truth for documents.
- The Auth Service is the source of truth for users and tokens.
- Redis is used as the canonical message broadcaster.
- Clients are only updated after changes are saved in the document database.

> **✅ One very important sentence**
> In this architecture, the final version of the document is always determined by the Document Service, not by the client itself.
