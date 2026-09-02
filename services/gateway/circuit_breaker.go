package main

import (
	"net/http"
	"sync"
	"time"
)

// Circuit state constants.
const (
	CircuitClosed   = iota // requests flow normally
	CircuitOpen            // requests are rejected immediately
	CircuitHalfOpen        // a single probe request is allowed through
)

// CircuitBreakerConfig holds tunable parameters.
type CircuitBreakerConfig struct {
	FailThreshold  int           // consecutive failures to trip open
	SuccessThreshold int         // consecutive successes in half-open to close
	OpenTimeout    time.Duration // how long to stay open before half-open
}

// DefaultCircuitBreakerConfig returns sensible defaults.
func DefaultCircuitBreakerConfig() CircuitBreakerConfig {
	return CircuitBreakerConfig{
		FailThreshold:    5,
		SuccessThreshold: 2,
		OpenTimeout:      10 * time.Second,
	}
}

// CircuitBreaker tracks failures per downstream service and transitions
// between Closed → Open → Half-Open → Closed.
type CircuitBreaker struct {
	mu               sync.Mutex
	state            int
	failCount        int
	successCount     int
	lastFailureTime  time.Time
	config           CircuitBreakerConfig
	name             string // label for metrics/logs
	onStateChange    func(from, to int) // optional hook for metrics
}

// NewCircuitBreaker creates a breaker with the given config and name.
func NewCircuitBreaker(name string, cfg CircuitBreakerConfig) *CircuitBreaker {
	return &CircuitBreaker{
		state:  CircuitClosed,
		config: cfg,
		name:   name,
	}
}

// State returns the current circuit state.
func (cb *CircuitBreaker) State() int {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == CircuitOpen {
		if time.Since(cb.lastFailureTime) > cb.config.OpenTimeout {
			cb.setStateUnlock(CircuitHalfOpen)
		}
	}
	return cb.state
}

// Allow returns true if the request should proceed (closed or half-open probe).
func (cb *CircuitBreaker) Allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == CircuitOpen {
		if time.Since(cb.lastFailureTime) > cb.config.OpenTimeout {
			cb.setStateUnlock(CircuitHalfOpen)
			return true // allow one probe
		}
		return false
	}
	return true // Closed or HalfOpen (probe allowed)
}

// RecordSuccess records a successful call.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == CircuitHalfOpen {
		cb.successCount++
		if cb.successCount >= cb.config.SuccessThreshold {
			cb.setStateUnlock(CircuitClosed)
			cb.failCount = 0
			cb.successCount = 0
		}
	} else {
		cb.failCount = 0
	}
}

// RecordFailure records a failed call.
func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failCount++
	cb.lastFailureTime = time.Now()

	if cb.state == CircuitHalfOpen {
		cb.setStateUnlock(CircuitOpen)
		cb.successCount = 0
	} else if cb.failCount >= cb.config.FailThreshold {
		cb.setStateUnlock(CircuitOpen)
	}
}

// setStateUnlock transitions state (caller must hold cb.mu).
func (cb *CircuitBreaker) setStateUnlock(to int) {
	if cb.state == to {
		return
	}
	if cb.onStateChange != nil {
		cb.onStateChange(cb.state, to)
	}
	cb.state = to
}

// Name returns the breaker's label.
func (cb *CircuitBreaker) Name() string { return cb.name }

// circuitBreakerHandler wraps an http.Handler with circuit breaker logic.
type circuitBreakerHandler struct {
	breaker *CircuitBreaker
	inner   http.Handler
	fallback http.Handler // served when circuit is open
}

// newCircuitBreakerHandler wraps inner with cb. When the circuit is open,
// fallback is served (defaults to a 503).
func newCircuitBreakerHandler(cb *CircuitBreaker, inner http.Handler, fallback http.Handler) http.Handler {
	if fallback == nil {
		fallback = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, `{"error":"service unavailable","circuit":"open"}`, http.StatusServiceUnavailable)
		})
	}
	return &circuitBreakerHandler{breaker: cb, inner: inner, fallback: fallback}
}

func (h *circuitBreakerHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !h.breaker.Allow() {
		h.breaker.RecordFailure()
		if gatewayCircuitBreakerRejections != nil {
			gatewayCircuitBreakerRejections.WithLabelValues(h.breaker.Name()).Inc()
		}
		h.fallback.ServeHTTP(w, r)
		return
	}

	rr := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
	h.inner.ServeHTTP(rr, r)

	if rr.status >= 500 {
		h.breaker.RecordFailure()
	} else {
		h.breaker.RecordSuccess()
	}
}

// statusRecorder captures the response status code.
type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

// stateName returns a human-readable name for a circuit state.
func stateName(s int) string {
	switch s {
	case CircuitClosed:
		return "closed"
	case CircuitOpen:
		return "open"
	case CircuitHalfOpen:
		return "half-open"
	default:
		return "unknown"
	}
}
