# Development Runbook

This document explains how to start the project, stop it, rebuild services, and determine when a restart is required.

## 1. Start all services

From the project root:

```bash
cd /home/ali/real-time-collaborative-document-system
docker compose up -d
```

This command starts all services defined in `docker-compose.yml`.

### Notes
- `redis`, `postgres`, `audit-postgres`, `zookeeper`, `kafka`, `jaeger`, `prometheus`, `grafana`, and other infrastructure services will start.
- `frontend`, `document-service`, `export-service`, `auth-service`, and `audit-service` will also start.

## 2. Stop all services

To stop and remove containers:

```bash
docker compose down
```

If you want to remove the local volumes too:

```bash
docker compose down -v
```

## 3. Start or stop a single service

### Start one service

```bash
docker compose up -d document-service
```

### Stop one service

```bash
docker compose stop document-service
```

### Remove one service container

```bash
docker compose rm -f document-service
```

## 4. Rebuild services

If you changed code in a service that does not use a bind mount or if the image needs to be rebuilt, run:

```bash
docker compose build document-service
docker compose up -d document-service
```

For multiple services:

```bash
docker compose build auth-service export-service
docker compose up -d auth-service export-service
```

## 5. Restart a service

If a service needs to reload without rebuilding the image:

```bash
docker compose restart document-service
```

## 6. Services that do not usually require rebuild

In the current `docker-compose.yml`, these services mount source code from the host and generally do not require rebuild for code changes:

- `document-service`
  - `./services/document_service:/app:cached`
  - Django development server normally reloads Python code.
- `export-service`
  - `./services/export_service:/app:cached`
  - Runs with `uvicorn --reload`.
- `auth-service`
  - `./services/auth_service:/app:cached`
  - Runs with `uvicorn --reload`.
- `frontend`
  - `./services/frontend:/app:cached`
  - Frontend files are mounted from the host; the frontend dev setup should pick up changes automatically.
- `audit-service`
  - `./services/audit_service:/app:cached`
  - Runs with `uvicorn --reload`.

## 7. Services that still require rebuild/restart

These services need build/restart for code changes because they are not mounted from the host or they run compiled binaries:

- `gateway`
  - Go service. Code changes require rebuilding and restarting the binary in the current compose setup.
  - For faster local development, run the gateway directly on the host:
    ```bash
    cd /home/ali/real-time-collaborative-document-system/services/gateway
go run .
    ```
  - Alternatively, you can change compose to bind-mount `./services/gateway` and use `go run .` instead of the built binary.

## 8. Important services and default URLs

- `gateway` → `http://localhost:8080`
- `frontend` → `http://localhost:3000`
- `document-service` → `http://localhost:8000`
- `export-service` → `http://localhost:8001`
- `auth-service` → `http://localhost:8002`
- `audit-service` → `http://localhost:8003`
- `postgres` → `localhost:5432`
- `audit-postgres` → `localhost:5434`
- `kafka` → `localhost:9092`
- `zookeeper` → `localhost:22181`

## 9. Full Docker reset

To remove containers and volumes and start fresh:

```bash
docker compose down -v
docker compose up -d
```

## 10. Practical note

If you are not changing code for a service, you do not need to rebuild or restart it. For mounted Python services, save the files and the service should reload code automatically.
