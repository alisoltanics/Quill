package main

import (
    "context"
    "io"
    "log"
    "net/http"
    "os"
    "os/signal"
    "time"

    "github.com/go-redis/redis/v8"
    "github.com/prometheus/client_golang/prometheus/promhttp"
    "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

func buildServer(cfg appConfig, hub *Hub, rdb *redis.Client) *http.Server {
    mux := http.NewServeMux()
    mux.Handle("/metrics", promhttp.Handler())

    if cfg.ObservabilityEnabled {
        mux.Handle("/ws", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            serveWs(hub, rdb, cfg, w, r)
        }), "/ws"))
        mux.Handle("/health", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            w.Header().Set("Access-Control-Allow-Origin", "*")
            if r.Method == http.MethodOptions {
                w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
                w.WriteHeader(http.StatusNoContent)
                return
            }
            w.WriteHeader(http.StatusOK)
            _, _ = w.Write([]byte("ok"))
        }), "/health"))
        mux.Handle("/document", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            w.Header().Set("Access-Control-Allow-Origin", "*")
            if r.Method == http.MethodOptions {
                w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
                w.WriteHeader(http.StatusNoContent)
                return
            }
            if cfg.DocumentServiceURL == "" {
                http.Error(w, "document service not configured", http.StatusBadGateway)
                return
            }
            client := &http.Client{Timeout: 5 * time.Second}
            req, _ := http.NewRequestWithContext(r.Context(), http.MethodGet, cfg.DocumentServiceURL+"/apply", nil)
            resp, err := client.Do(req)
            if err != nil {
                http.Error(w, "error contacting document service: "+err.Error(), http.StatusBadGateway)
                return
            }
            defer resp.Body.Close()
            w.Header().Set("Content-Type", "application/json")
            if resp.StatusCode != http.StatusOK {
                w.WriteHeader(resp.StatusCode)
            }
            _, _ = io.Copy(w, resp.Body)
        }), "/document"))
    } else {
        mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
            serveWs(hub, rdb, cfg, w, r)
        })
        mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
            w.Header().Set("Access-Control-Allow-Origin", "*")
            if r.Method == http.MethodOptions {
                w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
                w.WriteHeader(http.StatusNoContent)
                return
            }
            w.WriteHeader(http.StatusOK)
            _, _ = w.Write([]byte("ok"))
        })
        mux.HandleFunc("/document", func(w http.ResponseWriter, r *http.Request) {
            w.Header().Set("Access-Control-Allow-Origin", "*")
            if r.Method == http.MethodOptions {
                w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
                w.WriteHeader(http.StatusNoContent)
                return
            }
            if cfg.DocumentServiceURL == "" {
                http.Error(w, "document service not configured", http.StatusBadGateway)
                return
            }
            client := &http.Client{Timeout: 5 * time.Second}
            req, _ := http.NewRequest(http.MethodGet, cfg.DocumentServiceURL+"/apply", nil)
            resp, err := client.Do(req)
            if err != nil {
                http.Error(w, "error contacting document service: "+err.Error(), http.StatusBadGateway)
                return
            }
            defer resp.Body.Close()
            w.Header().Set("Content-Type", "application/json")
            if resp.StatusCode != http.StatusOK {
                w.WriteHeader(resp.StatusCode)
            }
            _, _ = io.Copy(w, resp.Body)
        })
    }

    return &http.Server{Addr: cfg.Addr, Handler: mux}
}

func runServer(cfg appConfig, hub *Hub, rdb *redis.Client) {
    srv := buildServer(cfg, hub, rdb)
    ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
    defer stop()

    go func() {
        log.Printf("starting gateway on %s", cfg.Addr)
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("listen: %s", err)
        }
    }()

    <-ctx.Done()
    shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
    _ = srv.Shutdown(shutdownCtx)
    log.Println("gateway stopped")
}
