package main

import (
    "os"
    "strings"
)

type appConfig struct {
    Addr                  string
    RedisAddr             string
    DocumentServiceURL    string
    ObservabilityEnabled  bool
    OTELServiceName       string
    OTELExporterEndpoint  string
}

func loadConfig() appConfig {
    cfg := appConfig{
        Addr:                 ":8080",
        RedisAddr:            os.Getenv("REDIS_ADDR"),
        DocumentServiceURL:   os.Getenv("DOCUMENT_SERVICE_URL"),
        ObservabilityEnabled: strings.EqualFold(os.Getenv("OBSERVABILITY_ENABLED"), "true"),
        OTELServiceName:      os.Getenv("OTEL_SERVICE_NAME"),
        OTELExporterEndpoint: os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    }

    if v := os.Getenv("ADDR"); v != "" {
        cfg.Addr = v
    }
    if cfg.OTELServiceName == "" {
        cfg.OTELServiceName = "realtime-gateway"
    }
    if cfg.OTELExporterEndpoint == "" {
        cfg.OTELExporterEndpoint = "http://jaeger:4318"
    }

    return cfg
}
