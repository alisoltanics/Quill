package main

import (
	"context"
	"encoding/json"
	"errors"
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
	conn      *websocket.Conn
	send      chan []byte
	docID     int
	closeOnce sync.Once
}

func (c *Client) closeSend() {
	c.closeOnce.Do(func() {
		close(c.send)
	})
}

type broadcastEvent struct {
	docID   int
	payload []byte
}

type Hub struct {
	mu        sync.Mutex
	rooms     map[int]map[*Client]struct{}
	broadcast chan broadcastEvent
}

func newHub() *Hub {
	return &Hub{
		rooms:     make(map[int]map[*Client]struct{}),
		broadcast: make(chan broadcastEvent, 256),
	}
}

func (h *Hub) run(ctx context.Context) {
	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			case event := <-h.broadcast:
				h.mu.Lock()
				room := h.rooms[event.docID]
				for client := range room {
					select {
					case client.send <- event.payload:
					default:
						delete(room, client)
						client.closeSend()
					}
				}
				if len(room) == 0 {
					delete(h.rooms, event.docID)
				}
				h.mu.Unlock()
			}
		}
	}()
}

func (h *Hub) register(c *Client) {
	gatewayWsConnections.Inc()
}

func (h *Hub) join(c *Client, docID int) {
	if docID <= 0 {
		return
	}

	h.mu.Lock()
	if c.docID == docID {
		h.mu.Unlock()
		return
	}
	if c.docID > 0 {
		if room, ok := h.rooms[c.docID]; ok {
			delete(room, c)
			if len(room) == 0 {
				delete(h.rooms, c.docID)
			}
		}
	}
	room, ok := h.rooms[docID]
	if !ok {
		room = make(map[*Client]struct{})
		h.rooms[docID] = room
	}
	room[c] = struct{}{}
	c.docID = docID
	h.mu.Unlock()
}

func (h *Hub) unregister(c *Client) {
	h.mu.Lock()
	if c.docID > 0 {
		if room, ok := h.rooms[c.docID]; ok {
			delete(room, c)
			if len(room) == 0 {
				delete(h.rooms, c.docID)
			}
		}
		c.docID = 0
	}
	h.mu.Unlock()
	c.closeSend()
	gatewayWsConnections.Dec()
}

func (h *Hub) broadcastToDoc(docID int, payload []byte) {
	if docID <= 0 {
		return
	}
	h.broadcast <- broadcastEvent{docID: docID, payload: payload}
}

type gatewayEnvelope struct {
	Type     string `json:"type"`
	DocID    int    `json:"docId"`
	ClientID string `json:"clientId"`
	Update   string `json:"update,omitempty"`
}

func decodeGatewayEnvelope(payload []byte) (*gatewayEnvelope, error) {
	var envelope gatewayEnvelope
	if err := json.Unmarshal(payload, &envelope); err != nil {
		return nil, err
	}
	if envelope.Type == "" || envelope.DocID <= 0 || envelope.ClientID == "" {
		return nil, errors.New("invalid websocket envelope")
	}
	return &envelope, nil
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

func (c *Client) readPump(ctx context.Context, h *Hub, rdb *redis.Client) {
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
		_, span := tracer.Start(ctx, "gateway.message.process")
		span.SetAttributes(
			attribute.Int("gateway.message.size", len(msg)),
			attribute.Bool("gateway.message.redis_enabled", rdb != nil),
		)

		envelope, err := decodeGatewayEnvelope(msg)
		if err != nil {
			span.RecordError(err)
			span.End()
			continue
		}

		switch envelope.Type {
		case "join", "update":
			h.join(c, envelope.DocID)
		default:
			span.End()
			continue
		}

		span.SetAttributes(
			attribute.String("gateway.message.type", envelope.Type),
			attribute.Int("gateway.message.doc_id", envelope.DocID),
		)

		// Persistence-first policy:
		// Client-originated updates are not fanned out directly by gateway.
		// Broadcast happens only after document-service saves to DB and publishes
		// canonical sync-state to Redis.

		span.End()
	}
}

func serveWs(h *Hub, rdb *redis.Client, w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("upgrade error: %v", err)
		return
	}
	client := &Client{conn: conn, send: make(chan []byte, 256)}
	h.register(client)
	go client.writePump()
	client.readPump(r.Context(), h, rdb)
}

func traceSpanFromContext(ctx context.Context, operation string) (context.Context, trace.Span) {
	return otel.Tracer("gateway.http").Start(ctx, operation)
}
