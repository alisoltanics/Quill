package main

import (
	"context"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

// corsMiddleware adds permissive CORS headers to every response.
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// newReverseProxy creates a reverse proxy to target, stripping stripPrefix from the path.
func newReverseProxy(target, stripPrefix string) http.Handler {
	u, _ := url.Parse(target)
	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.ModifyResponse = func(resp *http.Response) error {
		// Gateway is the single CORS boundary. Remove upstream CORS headers
		// to avoid duplicate Access-Control-Allow-Origin values.
		for name := range resp.Header {
			if strings.HasPrefix(strings.ToLower(name), "access-control-") {
				resp.Header.Del(name)
			}
		}
		return nil
	}
	director := proxy.Director
	proxy.Director = func(req *http.Request) {
		director(req)
		if stripPrefix != "" {
			req.URL.Path = req.URL.Path[len(stripPrefix):]
			if req.URL.Path == "" {
				req.URL.Path = "/"
			}
			req.URL.RawPath = ""
		}
		req.Header.Set("X-Forwarded-Host", req.Host)
	}
	return proxy
}

func buildServer(cfg appConfig, hub *Hub, rdb *redis.Client) *http.Server {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())

	wrap := func(h http.Handler, op string) http.Handler {
		if cfg.ObservabilityEnabled {
			return otelhttp.NewHandler(h, op)
		}
		return h
	}

	mux.Handle("/ws", wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		serveWs(hub, rdb, w, r)
	}), "/ws"))

	mux.Handle("/health", wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}), "/health"))

	if cfg.ExportServiceURL != "" {
		// Route export requests through the gateway so frontend only calls gateway.
		exportCB := NewCircuitBreaker("export-service", DefaultCircuitBreakerConfig())
		exportCB.onStateChange = func(from, to int) {
			gatewayCircuitBreakerTransitions.WithLabelValues("export-service", stateName(from), stateName(to)).Inc()
		}
		exportProxy := newCircuitBreakerHandler(exportCB, newReverseProxy(cfg.ExportServiceURL, "/api"), nil)
		mux.Handle("/api/export", wrap(exportProxy, "/api/export"))
		mux.Handle("/api/export/", wrap(exportProxy, "/api/export/"))
	}

	if cfg.DocumentServiceURL != "" {
		docCB := NewCircuitBreaker("document-service", DefaultCircuitBreakerConfig())
		docCB.onStateChange = func(from, to int) {
			gatewayCircuitBreakerTransitions.WithLabelValues("document-service", stateName(from), stateName(to)).Inc()
		}
		docProxy := newCircuitBreakerHandler(docCB, newReverseProxy(cfg.DocumentServiceURL, "/api"), nil)
		mux.Handle("/api/", wrap(docProxy, "/api/"))
	}

	return &http.Server{
		Addr:    cfg.Addr,
		Handler: corsMiddleware(jwtMiddleware(mux, "/health", "/metrics")),
	}
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
