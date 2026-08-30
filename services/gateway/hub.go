package main

import (
    "bytes"
    "context"
    "log"
    "net/http"
    "sync"
    "time"

    "github.com/go-redis/redis/v8"
    "github.com/gorilla/websocket"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

var upgrader = websocket.Upgrader{
    ReadBufferSize:  1024,
    WriteBufferSize: 1024,
    CheckOrigin:     func(r *http.Request) bool { return true },
}

type Client struct {
    conn *websocket.Conn
    send chan []byte
}

type Hub struct {
    mu        sync.Mutex
    clients   map[*Client]bool
    broadcast chan []byte
}

func newHub() *Hub {
    return &Hub{
        clients:   make(map[*Client]bool),
        broadcast: make(chan []byte, 256),
    }
}

func (h *Hub) run(ctx context.Context) {
    go func() {
        for {
            select {
            case <-ctx.Done():
                return
            case msg := <-h.broadcast:
                h.mu.Lock()
                for c := range h.clients {
                    select {
                    case c.send <- msg:
                    default:
                        close(c.send)
                        delete(h.clients, c)
                    }
                }
                h.mu.Unlock()
            }
        }
    }()
}

func (h *Hub) register(c *Client) {
    h.mu.Lock()
    h.clients[c] = true
    h.mu.Unlock()
    gatewayWsConnections.Inc()
}

func (h *Hub) unregister(c *Client) {
    h.mu.Lock()
    if _, ok := h.clients[c]; ok {
        delete(h.clients, c)
        close(c.send)
    }
    h.mu.Unlock()
    gatewayWsConnections.Dec()
}

func (c *Client) writePump() {
    ticker := time.NewTicker(54 * time.Second)
    defer func() {
        ticker.Stop()
        c.conn.Close()
    }()
    for {
        select {
        case msg, ok := <-c.send:
            _ = c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
            if !ok {
                _ = c.conn.WriteMessage(websocket.CloseMessage, []byte{})
                return
            }
            if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
                return
            }
        case <-ticker.C:
            _ = c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
            if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
                return
            }
        }
    }
}

func (c *Client) readPump(ctx context.Context, h *Hub, rdb *redis.Client, cfg appConfig) {
    defer func() {
        c.conn.Close()
        h.unregister(c)
    }()

    tracer := otel.Tracer("gateway.websocket")
    _ = c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
    c.conn.SetPongHandler(func(string) error {
        _ = c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
        return nil
    })

    for {
        _, msg, err := c.conn.ReadMessage()
        if err != nil {
            return
        }

        gatewayMessagesReceived.Inc()
        msgCtx, span := tracer.Start(ctx, "gateway.message.process")
        span.SetAttributes(
            attribute.Int("gateway.message.size", len(msg)),
            attribute.Bool("gateway.message.redis_enabled", rdb != nil),
        )

        if rdb != nil {
            if err := rdb.Publish(msgCtx, "gateway:events", msg).Err(); err != nil {
                span.RecordError(err)
            }
            gatewayRedisPublishes.Inc()
        } else {
            h.broadcast <- msg
        }

        if cfg.DocumentServiceURL != "" {
            go func(payload []byte, parent context.Context) {
                docCtx, docSpan := otel.Tracer("gateway.document_service").Start(parent, "document_service.apply")
                defer docSpan.End()

                start := time.Now()
                url := cfg.DocumentServiceURL + "/apply"
                client := &http.Client{Timeout: 5 * time.Second}
                req, _ := http.NewRequestWithContext(docCtx, http.MethodPost, url, bytes.NewReader(payload))
                req.Header.Set("Content-Type", "application/json")
                docSpan.SetAttributes(
                    attribute.String("http.method", req.Method),
                    attribute.String("http.url", url),
                )

                resp, err := client.Do(req)
                gatewayDocumentServiceRequests.Inc()
                gatewayDocumentServiceLatency.Observe(time.Since(start).Seconds())
                if err != nil {
                    log.Printf("document service request error: %v", err)
                    docSpan.RecordError(err)
                    return
                }
                defer resp.Body.Close()
                docSpan.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

                respBody := new(bytes.Buffer)
                _, _ = respBody.ReadFrom(resp.Body)
                result := respBody.Bytes()

                if rdb != nil {
                    if err := rdb.Publish(docCtx, "gateway:events", result).Err(); err != nil {
                        docSpan.RecordError(err)
                    }
                    gatewayRedisPublishes.Inc()
                } else {
                    h.broadcast <- result
                }
            }(append([]byte(nil), msg...), msgCtx)
        }

        span.End()
    }
}

func serveWs(h *Hub, rdb *redis.Client, cfg appConfig, w http.ResponseWriter, r *http.Request) {
    conn, err := upgrader.Upgrade(w, r, nil)
    if err != nil {
        log.Printf("upgrade error: %v", err)
        return
    }
    client := &Client{conn: conn, send: make(chan []byte, 256)}
    h.register(client)
    go client.writePump()
    client.readPump(r.Context(), h, rdb, cfg)
}

func traceSpanFromContext(ctx context.Context, operation string) (context.Context, trace.Span) {
    return otel.Tracer("gateway.http").Start(ctx, operation)
}
