package main

import (
	"context"
	"encoding/json"
	"testing"
	"time"
)

// ─── encodeGatewayEnvelope / decodeGatewayEnvelope ────────────────────────────

func TestEncodeDecodeEnvelope_Roundtrip(t *testing.T) {
	env := gatewayEnvelope{
		Type:     "join",
		DocID:    42,
		ClientID: "client-abc",
		Update:   "dGVzdA==",
	}
	encoded, err := encodeGatewayEnvelope(env)
	if err != nil {
		t.Fatalf("encode error: %v", err)
	}

	decoded, err := decodeGatewayEnvelope(encoded)
	if err != nil {
		t.Fatalf("decode error: %v", err)
	}

	if decoded.Type != "join" {
		t.Errorf("Type = %q, want %q", decoded.Type, "join")
	}
	if decoded.DocID != 42 {
		t.Errorf("DocID = %d, want %d", decoded.DocID, 42)
	}
	if decoded.ClientID != "client-abc" {
		t.Errorf("ClientID = %q, want %q", decoded.ClientID, "client-abc")
	}
	if decoded.Update != "dGVzdA==" {
		t.Errorf("Update = %q, want %q", decoded.Update, "dGVzdA==")
	}
}

func TestDecodeEnvelope_WithCursor(t *testing.T) {
	env := gatewayEnvelope{
		Type:     "cursor-update",
		DocID:    10,
		ClientID: "client-1",
		Cursor:   &cursorData{Email: "alice@test.com", Position: 50},
	}
	encoded, err := encodeGatewayEnvelope(env)
	if err != nil {
		t.Fatalf("encode error: %v", err)
	}

	decoded, err := decodeGatewayEnvelope(encoded)
	if err != nil {
		t.Fatalf("decode error: %v", err)
	}

	if decoded.Cursor == nil {
		t.Fatal("Cursor is nil")
	}
	if decoded.Cursor.Email != "alice@test.com" {
		t.Errorf("Cursor.Email = %q, want %q", decoded.Cursor.Email, "alice@test.com")
	}
	if decoded.Cursor.Position != 50 {
		t.Errorf("Cursor.Position = %d, want %d", decoded.Cursor.Position, 50)
	}
}

func TestDecodeEnvelope_WithUsers(t *testing.T) {
	env := gatewayEnvelope{
		Type:     "presence-update",
		DocID:    5,
		ClientID: "gateway",
		Users:    []string{"alice@test.com", "bob@test.com"},
	}
	encoded, err := encodeGatewayEnvelope(env)
	if err != nil {
		t.Fatalf("encode error: %v", err)
	}

	decoded, err := decodeGatewayEnvelope(encoded)
	if err != nil {
		t.Fatalf("decode error: %v", err)
	}

	if len(decoded.Users) != 2 {
		t.Fatalf("Users len = %d, want 2", len(decoded.Users))
	}
	if decoded.Users[0] != "alice@test.com" {
		t.Errorf("Users[0] = %q, want %q", decoded.Users[0], "alice@test.com")
	}
}

func TestDecodeEnvelope_EmptyType(t *testing.T) {
	env := gatewayEnvelope{Type: "", DocID: 1, ClientID: "c"}
	encoded, _ := json.Marshal(env)
	_, err := decodeGatewayEnvelope(encoded)
	if err == nil {
		t.Fatal("expected error for empty type")
	}
}

func TestDecodeEnvelope_ZeroDocID(t *testing.T) {
	env := gatewayEnvelope{Type: "join", DocID: 0, ClientID: "c"}
	encoded, _ := json.Marshal(env)
	_, err := decodeGatewayEnvelope(encoded)
	if err == nil {
		t.Fatal("expected error for zero docID")
	}
}

func TestDecodeEnvelope_NegativeDocID(t *testing.T) {
	env := gatewayEnvelope{Type: "join", DocID: -1, ClientID: "c"}
	encoded, _ := json.Marshal(env)
	_, err := decodeGatewayEnvelope(encoded)
	if err == nil {
		t.Fatal("expected error for negative docID")
	}
}

func TestDecodeEnvelope_EmptyClientID(t *testing.T) {
	env := gatewayEnvelope{Type: "join", DocID: 1, ClientID: ""}
	encoded, _ := json.Marshal(env)
	_, err := decodeGatewayEnvelope(encoded)
	if err == nil {
		t.Fatal("expected error for empty clientID")
	}
}

func TestDecodeEnvelope_InvalidJSON(t *testing.T) {
	_, err := decodeGatewayEnvelope([]byte("not json"))
	if err == nil {
		t.Fatal("expected error for invalid JSON")
	}
}

func TestDecodeEnvelope_EmptyPayload(t *testing.T) {
	_, err := decodeGatewayEnvelope([]byte("{}"))
	if err == nil {
		t.Fatal("expected error for empty payload")
	}
}

// ─── Hub.join ─────────────────────────────────────────────────────────────────

func TestHub_Join(t *testing.T) {
	h := newHub()
	c := &Client{send: make(chan []byte, 256)}

	h.join(c, 10)

	if c.docID != 10 {
		t.Errorf("docID = %d, want %d", c.docID, 10)
	}
	h.mu.Lock()
	room, ok := h.rooms[10]
	h.mu.Unlock()
	if !ok {
		t.Fatal("room 10 not created")
	}
	if _, ok := room[c]; !ok {
		t.Fatal("client not in room")
	}
}

func TestHub_JoinInvalidDocID(t *testing.T) {
	h := newHub()
	c := &Client{send: make(chan []byte, 256)}

	h.join(c, 0)
	if c.docID != 0 {
		t.Errorf("docID = %d, want 0", c.docID)
	}
	h.join(c, -1)
	if c.docID != 0 {
		t.Errorf("docID = %d, want 0 after negative join", c.docID)
	}
}

func TestHub_JoinSameDocID(t *testing.T) {
	h := newHub()
	c := &Client{send: make(chan []byte, 256)}

	h.join(c, 10)
	h.join(c, 10) // join same doc again

	h.mu.Lock()
	room := h.rooms[10]
	h.mu.Unlock()
	if len(room) != 1 {
		t.Errorf("room has %d clients, want 1", len(room))
	}
}

func TestHub_JoinMovesFromOldRoom(t *testing.T) {
	h := newHub()
	c := &Client{send: make(chan []byte, 256)}

	h.join(c, 10)
	h.join(c, 20)

	h.mu.Lock()
	room10, ok10 := h.rooms[10]
	room20, ok20 := h.rooms[20]
	h.mu.Unlock()

	if ok10 && len(room10) > 0 {
		t.Error("client still in old room 10")
	}
	if !ok20 {
		t.Fatal("room 20 not created")
	}
	if _, ok := room20[c]; !ok {
		t.Fatal("client not in new room 20")
	}
	if c.docID != 20 {
		t.Errorf("docID = %d, want 20", c.docID)
	}
}

func TestHub_JoinMultipleClients(t *testing.T) {
	h := newHub()
	c1 := &Client{send: make(chan []byte, 256)}
	c2 := &Client{send: make(chan []byte, 256)}

	h.join(c1, 10)
	h.join(c2, 10)

	h.mu.Lock()
	room := h.rooms[10]
	h.mu.Unlock()
	if len(room) != 2 {
		t.Errorf("room has %d clients, want 2", len(room))
	}
}

// ─── Hub.broadcastToDoc / broadcastToDocExcept ────────────────────────────────

func TestHub_BroadcastToDoc(t *testing.T) {
	h := newHub()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	h.run(ctx)

	c1 := &Client{send: make(chan []byte, 256)}
	c2 := &Client{send: make(chan []byte, 256)}
	h.join(c1, 1)
	h.join(c2, 1)

	payload := []byte(`{"type":"update","docId":1}`)
	h.broadcastToDoc(1, payload)

	select {
	case msg := <-c1.send:
		if string(msg) != string(payload) {
			t.Errorf("c1 got %q, want %q", msg, payload)
		}
	case <-time.After(time.Second):
		t.Fatal("c1 did not receive message")
	}

	select {
	case msg := <-c2.send:
		if string(msg) != string(payload) {
			t.Errorf("c2 got %q, want %q", msg, payload)
		}
	case <-time.After(time.Second):
		t.Fatal("c2 did not receive message")
	}
}

func TestHub_BroadcastToDocExcept(t *testing.T) {
	h := newHub()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	h.run(ctx)

	c1 := &Client{send: make(chan []byte, 256)}
	c2 := &Client{send: make(chan []byte, 256)}
	h.join(c1, 1)
	h.join(c2, 1)

	payload := []byte(`{"type":"update","docId":1}`)
	h.broadcastToDocExcept(1, payload, c1)

	// c2 should receive
	select {
	case msg := <-c2.send:
		if string(msg) != string(payload) {
			t.Errorf("c2 got %q, want %q", msg, payload)
		}
	case <-time.After(time.Second):
		t.Fatal("c2 did not receive message")
	}

	// c1 should NOT receive
	select {
	case <-c1.send:
		t.Error("c1 should not have received message")
	case <-time.After(100 * time.Millisecond):
		// expected
	}
}

func TestHub_BroadcastInvalidDocID(t *testing.T) {
	h := newHub()
	h.broadcastToDoc(0, []byte("test"))
	h.broadcastToDoc(-1, []byte("test"))

	// broadcastToDocExcept with invalid docID should not panic
	h.broadcastToDocExcept(0, []byte("test"), nil)
	h.broadcastToDocExcept(-1, []byte("test"), nil)
}

// ─── Client.closeSend ────────────────────────────────────────────────────────

func TestClient_CloseSend(t *testing.T) {
	c := &Client{send: make(chan []byte, 256)}
	c.closeSend()
	// Calling again should not panic (idempotent)
	c.closeSend()
}

// ─── Hub room cleanup ────────────────────────────────────────────────────────

func TestHub_BroadcastRemovesEmptyRoom(t *testing.T) {
	h := newHub()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	h.run(ctx)

	// Create room with one client, then close its send channel to force removal
	c := &Client{send: make(chan []byte, 1)}
	h.join(c, 1)

	// Fill the buffer so broadcast drops the client
	c.send <- []byte("fill")

	payload := []byte(`{"type":"test"}`)
	h.broadcastToDoc(1, payload)

	// Wait for broadcast to process
	time.Sleep(200 * time.Millisecond)

	h.mu.Lock()
	_, exists := h.rooms[1]
	h.mu.Unlock()
	if exists {
		t.Error("empty room should have been removed")
	}
}
