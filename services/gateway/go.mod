module github.com/example/realtime-gateway

go 1.22

toolchain go1.22.12

require (
	github.com/go-redis/redis/v8 v8.11.5
	github.com/gorilla/websocket v1.5.0
	github.com/prometheus/client_golang v1.17.0
	go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp v0.55.0
	go.opentelemetry.io/otel v1.30.0
	go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp v1.30.0
	go.opentelemetry.io/otel/sdk v1.30.0
)

require github.com/golang-jwt/jwt/v5 v5.3.1 // indirect
