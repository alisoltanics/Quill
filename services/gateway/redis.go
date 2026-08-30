package main

import (
    "context"
    "log"

    "github.com/go-redis/redis/v8"
)

func connectRedis(addr string) *redis.Client {
    if addr == "" {
        return nil
    }
    client := redis.NewClient(&redis.Options{Addr: addr})
    if err := client.Ping(context.Background()).Err(); err != nil {
        log.Printf("redis unavailable: %v", err)
        return nil
    }
    return client
}

func startRedisSubscriber(ctx context.Context, h *Hub, rdb *redis.Client) {
    if rdb == nil {
        return
    }
    pubsub := rdb.Subscribe(ctx, "gateway:events")
    ch := pubsub.Channel()
    go func() {
        for {
            select {
            case <-ctx.Done():
                _ = pubsub.Close()
                return
            case msg := <-ch:
                if msg != nil {
                    h.broadcast <- []byte(msg.Payload)
                }
            }
        }
    }()
}
