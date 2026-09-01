package main

import (
    "context"
    "flag"
    "log"
    "os"
)

var addr = flag.String("addr", ":8080", "http service address")

func main() {
    flag.Parse()

    cfg := loadConfig()
    if *addr != ":8080" {
        cfg.Addr = *addr
    }

    ctx, stop := context.WithCancel(context.Background())
    defer stop()

    hub := newHub()
    hub.run(ctx)

    rdb := connectRedis(cfg.RedisAddr)
    if rdb != nil {
        startRedisSubscriber(ctx, hub, rdb)
        log.Printf("redis enabled, address=%s", cfg.RedisAddr)
    }

    if cfg.ObservabilityEnabled {
        shutdownTracer, err := initTracer(cfg)
        if err != nil {
            log.Printf("tracer init warning: %v", err)
        } else {
            defer func() {
                if shutdownErr := shutdownTracer(context.Background()); shutdownErr != nil {
                    log.Printf("trace shutdown error: %v", shutdownErr)
                }
            }()
        }
    } else {
        log.Println("observability disabled via OBSERVABILITY_ENABLED=false")
    }

    if cfg.DocumentServiceURL != "" {
        log.Printf("document service enabled, url=%s", cfg.DocumentServiceURL)
    }
    if cfg.ExportServiceURL != "" {
        log.Printf("export service enabled, url=%s", cfg.ExportServiceURL)
    }

    runServer(cfg, hub, rdb)
    _ = os.Stdout.Sync()
    log.Println("gateway exit complete")
}
