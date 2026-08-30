
# Frontend — Next.js + TypeScript

Simple frontend that connects to the Go gateway via WebSocket and provides
a minimal UI demonstrating realtime collaborative document updates.

Run locally

```bash
cd services/frontend
npm install
npm run dev
```

The app will run on `http://localhost:3000` by default. Set `NEXT_PUBLIC_WS_URL`
to point to the gateway WebSocket (default `ws://localhost:8080/ws`).

Environment example:

```bash
export NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws
npm run dev
```
