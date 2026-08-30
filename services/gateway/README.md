Gateway service (Go)
====================

This is a minimal WebSocket Gateway implemented in Go. It accepts WebSocket
connections at `/ws`, broadcasts messages to connected clients, and provides a
simple `/health` endpoint.

Key features
- Local broadcast to all connected clients.
- Optional Redis publish/subscribe for cross-instance message delivery. Set
  `REDIS_ADDR` environment variable (e.g. `localhost:6379`) to enable.

Run locally (development)

1. Install dependencies and build:

   ```bash
   cd services/gateway
   go mod tidy
   go run . -addr :8080
   ```

2. Connect a WebSocket client (e.g. browser or `wscat`) to `ws://localhost:8080/ws`.

Docker (optional)

Build and run the Docker image (example):

```bash
docker build -t rt-gateway:dev .
docker run -e REDIS_ADDR=redis:6379 -p 8080:8080 rt-gateway:dev
```

Notes for beginners
- The code is heavily commented to explain each step. Look at `main.go` for
  explanations of the client hub, read/write pumps, and Redis integration.
