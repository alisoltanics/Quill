package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// --- State machine tests ---

func TestCircuitBreaker_StartsClosed(t *testing.T) {
	cb := NewCircuitBreaker("test", DefaultCircuitBreakerConfig())
	if cb.State() != CircuitClosed {
		t.Errorf("initial state = %d, want %d", cb.State(), CircuitClosed)
	}
}

func TestCircuitBreaker_OpensAfterThreshold(t *testing.T) {
	cfg := CircuitBreakerConfig{FailThreshold: 3, SuccessThreshold: 2, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	if cb.State() != CircuitOpen {
		t.Errorf("state = %d, want CircuitOpen", cb.State())
	}
}

func TestCircuitBreaker_RejectsWhenOpen(t *testing.T) {
	cfg := CircuitBreakerConfig{FailThreshold: 2, SuccessThreshold: 1, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)
	cb.RecordFailure()
	cb.RecordFailure()

	if cb.Allow() {
		t.Error("Allow() = true, want false when open")
	}
}

func TestCircuitBreaker_HalfOpenAfterTimeout(t *testing.T) {
	cfg := CircuitBreakerConfig{FailThreshold: 2, SuccessThreshold: 1, OpenTimeout: 50 * time.Millisecond}
	cb := NewCircuitBreaker("test", cfg)
	cb.RecordFailure()
	cb.RecordFailure()

	time.Sleep(80 * time.Millisecond)

	if !cb.Allow() {
		t.Error("Allow() = false, want true after timeout (half-open)")
	}
	if cb.State() != CircuitHalfOpen {
		t.Errorf("state = %d, want CircuitHalfOpen", cb.State())
	}
}

func TestCircuitBreaker_ClosesFromHalfOpenOnSuccess(t *testing.T) {
	cfg := CircuitBreakerConfig{FailThreshold: 2, SuccessThreshold: 2, OpenTimeout: 50 * time.Millisecond}
	cb := NewCircuitBreaker("test", cfg)
	cb.RecordFailure()
	cb.RecordFailure()

	time.Sleep(80 * time.Millisecond)
	cb.Allow() // transition to half-open
	cb.RecordSuccess()
	cb.RecordSuccess()

	if cb.State() != CircuitClosed {
		t.Errorf("state = %d, want CircuitClosed", cb.State())
	}
}

func TestCircuitBreaker_ReopensFromHalfOpenOnFailure(t *testing.T) {
	cfg := CircuitBreakerConfig{FailThreshold: 2, SuccessThreshold: 2, OpenTimeout: 50 * time.Millisecond}
	cb := NewCircuitBreaker("test", cfg)
	cb.RecordFailure()
	cb.RecordFailure()

	time.Sleep(80 * time.Millisecond)
	cb.Allow() // half-open
	cb.RecordFailure()

	if cb.State() != CircuitOpen {
		t.Errorf("state = %d, want CircuitOpen", cb.State())
	}
}

func TestCircuitBreaker_SuccessResetsFailCount(t *testing.T) {
	cfg := CircuitBreakerConfig{FailThreshold: 3, SuccessThreshold: 1, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)

	cb.RecordFailure()
	cb.RecordFailure()
	cb.RecordSuccess() // resets

	cb.RecordFailure()
	cb.RecordFailure()
	if cb.State() != CircuitClosed {
		t.Error("success should have reset fail count")
	}
}

func TestCircuitBreaker_Name(t *testing.T) {
	cb := NewCircuitBreaker("my-service", DefaultCircuitBreakerConfig())
	if cb.Name() != "my-service" {
		t.Errorf("Name() = %q, want %q", cb.Name(), "my-service")
	}
}

// --- HTTP handler tests ---

func TestCircuitBreakerHandler_AllowsWhenClosed(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	cb := NewCircuitBreaker("test", DefaultCircuitBreakerConfig())
	handler := newCircuitBreakerHandler(cb, inner, nil)

	req := httptest.NewRequest("GET", "/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusOK)
	}
}

func TestCircuitBreakerHandler_Returns503WhenOpen(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	cfg := CircuitBreakerConfig{FailThreshold: 1, SuccessThreshold: 1, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)
	cb.RecordFailure() // trip the breaker

	handler := newCircuitBreakerHandler(cb, inner, nil)
	req := httptest.NewRequest("GET", "/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusServiceUnavailable)
	}
	if !strings.Contains(rr.Body.String(), "circuit") {
		t.Error("response should mention circuit state")
	}
}

func TestCircuitBreakerHandler_Records5xxAsFailure(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	cfg := CircuitBreakerConfig{FailThreshold: 2, SuccessThreshold: 1, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)
	handler := newCircuitBreakerHandler(cb, inner, nil)

	for i := 0; i < 2; i++ {
		req := httptest.NewRequest("GET", "/test", nil)
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, req)
	}

	if cb.State() != CircuitOpen {
		t.Errorf("state = %d, want CircuitOpen after 5xx errors", cb.State())
	}
}

func TestCircuitBreakerHandler_Records2xxAsSuccess(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	cfg := CircuitBreakerConfig{FailThreshold: 3, SuccessThreshold: 1, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)

	handler := newCircuitBreakerHandler(cb, inner, nil)
	req := httptest.NewRequest("GET", "/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if cb.failCount != 0 {
		t.Errorf("failCount = %d, want 0", cb.failCount)
	}
}

func TestCircuitBreakerHandler_CustomFallback(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	cfg := CircuitBreakerConfig{FailThreshold: 1, SuccessThreshold: 1, OpenTimeout: 1 * time.Hour}
	cb := NewCircuitBreaker("test", cfg)
	cb.RecordFailure()

	fallback := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte("custom fallback"))
	})
	handler := newCircuitBreakerHandler(cb, inner, fallback)

	req := httptest.NewRequest("GET", "/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadGateway {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusBadGateway)
	}
	if rr.Body.String() != "custom fallback" {
		t.Errorf("body = %q, want %q", rr.Body.String(), "custom fallback")
	}
}

func TestStateName(t *testing.T) {
	tests := []struct {
		state int
		want  string
	}{
		{CircuitClosed, "closed"},
		{CircuitOpen, "open"},
		{CircuitHalfOpen, "half-open"},
		{99, "unknown"},
	}
	for _, tt := range tests {
		if got := stateName(tt.state); got != tt.want {
			t.Errorf("stateName(%d) = %q, want %q", tt.state, got, tt.want)
		}
	}
}
