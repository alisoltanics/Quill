package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/go-redis/redis/v8"
)

const presenceTTL = 90 * time.Second

func presenceKey(docID int) string {
	return fmt.Sprintf("doc:%d:online", docID)
}

// addPresence adds an email to the online set for a document with a TTL score.
func addPresence(ctx context.Context, rdb *redis.Client, docID int, email string) {
	if rdb == nil || email == "" {
		return
	}
	key := presenceKey(docID)
	score := float64(time.Now().UnixMilli())
	rdb.ZAdd(ctx, key, &redis.Z{Score: score, Member: email})
	rdb.Expire(ctx, key, presenceTTL)
}

// removePresence removes an email from the online set for a document.
func removePresence(ctx context.Context, rdb *redis.Client, docID int, email string) {
	if rdb == nil || email == "" {
		return
	}
	rdb.ZRem(ctx, presenceKey(docID), email)
}

// getOnlineUsers returns the list of online emails for a document,
// after cleaning up stale entries older than presenceTTL.
func getOnlineUsers(ctx context.Context, rdb *redis.Client, docID int) ([]string, error) {
	if rdb == nil {
		return nil, nil
	}
	key := presenceKey(docID)
	cutoff := float64(time.Now().Add(-presenceTTL).UnixMilli())
	rdb.ZRemRangeByScore(ctx, key, "0", fmt.Sprintf("%f", cutoff))

	members, err := rdb.ZRange(ctx, key, 0, -1).Result()
	if err != nil {
		return nil, err
	}
	return members, nil
}

// broadcastPresence fetches the full online user list and publishes a
// presence-update message to Redis so all gateway instances can relay it.
func broadcastPresence(ctx context.Context, rdb *redis.Client, h *Hub, docID int) {
	users, err := getOnlineUsers(ctx, rdb, docID)
	if err != nil {
		log.Printf("presence: failed to get online users for doc %d: %v", docID, err)
		return
	}

	envelope := gatewayEnvelope{
		Type:     "presence-update",
		DocID:    docID,
		ClientID: "gateway",
		Users:    users,
	}

	payload, err := encodeGatewayEnvelope(envelope)
	if err != nil {
		log.Printf("presence: failed to encode envelope: %v", err)
		return
	}

	rdb.Publish(ctx, "gateway:events", payload)
}
