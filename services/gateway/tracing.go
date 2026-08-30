package main

import (
    "context"
    "log"
    "net/url"
    "strings"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
    "go.opentelemetry.io/otel/sdk/resource"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
    semconv "go.opentelemetry.io/otel/semconv/v1.21.0"
)

func initTracer(cfg appConfig) (func(context.Context) error, error) {
    endpoint := cfg.OTELExporterEndpoint
    serviceName := cfg.OTELServiceName

    host := "jaeger:4318"
    if endpoint != "" {
        if parsed, err := url.Parse(endpoint); err == nil && parsed.Host != "" {
            host = parsed.Host
        } else if strings.Contains(endpoint, ":") {
            host = endpoint
        }
    }

    exporter, err := otlptracehttp.New(context.Background(),
        otlptracehttp.WithEndpoint(host),
        otlptracehttp.WithInsecure(),
    )
    if err != nil {
        return nil, err
    }

    res, err := resource.New(context.Background(),
        resource.WithAttributes(
            semconv.ServiceNameKey.String(serviceName),
            semconv.ServiceVersionKey.String("1.0.0"),
        ),
    )
    if err != nil {
        log.Printf("failed to create tracing resource: %v", err)
        res, _ = resource.Default()
    }

    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exporter),
        sdktrace.WithResource(res),
    )
    otel.SetTracerProvider(tp)

    return tp.Shutdown, nil
}
