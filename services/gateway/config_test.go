package main

import (
	"os"
	"testing"
)

func TestLoadConfig_Defaults(t *testing.T) {
	// Clear all env vars
	envVars := []string{"ADDR", "REDIS_ADDR", "DOCUMENT_SERVICE_URL", "EXPORT_SERVICE_URL", "FASTAPI_SERVICE_URL", "OBSERVABILITY_ENABLED", "OTEL_SERVICE_NAME", "OTEL_EXPORTER_OTLP_ENDPOINT"}
	for _, v := range envVars {
		os.Unsetenv(v)
	}

	cfg := loadConfig()

	if cfg.Addr != ":8080" {
		t.Errorf("Addr = %q, want %q", cfg.Addr, ":8080")
	}
	if cfg.RedisAddr != "" {
		t.Errorf("RedisAddr = %q, want empty", cfg.RedisAddr)
	}
	if cfg.DocumentServiceURL != "" {
		t.Errorf("DocumentServiceURL = %q, want empty", cfg.DocumentServiceURL)
	}
	if cfg.ExportServiceURL != "" {
		t.Errorf("ExportServiceURL = %q, want empty", cfg.ExportServiceURL)
	}
	if cfg.ObservabilityEnabled {
		t.Error("ObservabilityEnabled should be false by default")
	}
	if cfg.OTELServiceName != "realtime-gateway" {
		t.Errorf("OTELServiceName = %q, want %q", cfg.OTELServiceName, "realtime-gateway")
	}
	if cfg.OTELExporterEndpoint != "http://jaeger:4318" {
		t.Errorf("OTELExporterEndpoint = %q, want %q", cfg.OTELExporterEndpoint, "http://jaeger:4318")
	}
}

func TestLoadConfig_EnvOverrides(t *testing.T) {
	os.Setenv("ADDR", ":9090")
	os.Setenv("REDIS_ADDR", "redis:6379")
	os.Setenv("DOCUMENT_SERVICE_URL", "http://doc-svc:8000")
	os.Setenv("EXPORT_SERVICE_URL", "http://export-svc:8001")
	os.Setenv("OBSERVABILITY_ENABLED", "true")
	defer func() {
		os.Unsetenv("ADDR")
		os.Unsetenv("REDIS_ADDR")
		os.Unsetenv("DOCUMENT_SERVICE_URL")
		os.Unsetenv("EXPORT_SERVICE_URL")
		os.Unsetenv("OBSERVABILITY_ENABLED")
	}()

	cfg := loadConfig()

	if cfg.Addr != ":9090" {
		t.Errorf("Addr = %q, want %q", cfg.Addr, ":9090")
	}
	if cfg.RedisAddr != "redis:6379" {
		t.Errorf("RedisAddr = %q, want %q", cfg.RedisAddr, "redis:6379")
	}
	if cfg.DocumentServiceURL != "http://doc-svc:8000" {
		t.Errorf("DocumentServiceURL = %q, want %q", cfg.DocumentServiceURL, "http://doc-svc:8000")
	}
	if cfg.ExportServiceURL != "http://export-svc:8001" {
		t.Errorf("ExportServiceURL = %q, want %q", cfg.ExportServiceURL, "http://export-svc:8001")
	}
	if !cfg.ObservabilityEnabled {
		t.Error("ObservabilityEnabled should be true")
	}
}

func TestLoadConfig_FallbackFastAPIURL(t *testing.T) {
	os.Unsetenv("EXPORT_SERVICE_URL")
	os.Setenv("FASTAPI_SERVICE_URL", "http://fastapi:8001")
	defer os.Unsetenv("FASTAPI_SERVICE_URL")

	cfg := loadConfig()

	if cfg.ExportServiceURL != "http://fastapi:8001" {
		t.Errorf("ExportServiceURL = %q, want %q", cfg.ExportServiceURL, "http://fastapi:8001")
	}
}

func TestLoadConfig_ObservabilityValues(t *testing.T) {
	tests := []struct {
		val   string
		want  bool
	}{
		{"true", true},
		{"TRUE", true},
		{"True", true},
		{"1", false},
		{"false", false},
		{"", false},
	}
	for _, tt := range tests {
		os.Setenv("OBSERVABILITY_ENABLED", tt.val)
		cfg := loadConfig()
		if cfg.ObservabilityEnabled != tt.want {
			t.Errorf("OBSERVABILITY_ENABLED=%q: got %v, want %v", tt.val, cfg.ObservabilityEnabled, tt.want)
		}
	}
	os.Unsetenv("OBSERVABILITY_ENABLED")
}
