package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const testSecret = "test-gateway-secret"

func init() {
	os.Setenv("JWT_SECRET", testSecret)
	jwtSecret = []byte(testSecret)
}

func makeAccessToken(sub, email string, exp time.Time) string {
	claims := jwtClaims{
		Email:     email,
		TokenType: "access",
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   sub,
			ExpiresAt: jwt.NewNumericDate(exp),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	s, _ := token.SignedString(jwtSecret)
	return s
}

func makeRefreshToken(sub string, exp time.Time) string {
	claims := jwtClaims{
		TokenType: "refresh",
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   sub,
			ExpiresAt: jwt.NewNumericDate(exp),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	s, _ := token.SignedString(jwtSecret)
	return s
}

// ─── extractToken ────────────────────────────────────────────────────────────

func TestExtractToken_BearerHeader(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.Header.Set("Authorization", "Bearer my-token-123")
	tok, err := extractToken(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tok != "my-token-123" {
		t.Errorf("got %q, want %q", tok, "my-token-123")
	}
}

func TestExtractToken_BearerCaseInsensitive(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.Header.Set("Authorization", "bearer my-token-123")
	tok, err := extractToken(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tok != "my-token-123" {
		t.Errorf("got %q, want %q", tok, "my-token-123")
	}
}

func TestExtractToken_QueryParam(t *testing.T) {
	r := httptest.NewRequest("GET", "/ws?token=abc123", nil)
	tok, err := extractToken(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tok != "abc123" {
		t.Errorf("got %q, want %q", tok, "abc123")
	}
}

func TestExtractToken_HeaderTakesPrecedence(t *testing.T) {
	r := httptest.NewRequest("GET", "/ws?token=query-tok", nil)
	r.Header.Set("Authorization", "Bearer header-tok")
	tok, err := extractToken(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tok != "header-tok" {
		t.Errorf("got %q, want %q", tok, "header-tok")
	}
}

func TestExtractToken_NoToken(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	_, err := extractToken(r)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
}

func TestExtractToken_MalformedHeader(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.Header.Set("Authorization", "Token abc")
	_, err := extractToken(r)
	if err == nil {
		t.Fatal("expected error for malformed header")
	}
}

func TestExtractToken_MalformedHeaderNoSpace(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.Header.Set("Authorization", "Bearertoken123")
	_, err := extractToken(r)
	if err == nil {
		t.Fatal("expected error for malformed header")
	}
}

// ─── verifyAccessToken ───────────────────────────────────────────────────────

func TestVerifyAccessToken_Valid(t *testing.T) {
	tok := makeAccessToken("1", "user@example.com", time.Now().Add(time.Hour))
	claims, err := verifyAccessToken(tok)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if claims.Email != "user@example.com" {
		t.Errorf("email = %q, want %q", claims.Email, "user@example.com")
	}
	if claims.TokenType != "access" {
		t.Errorf("type = %q, want %q", claims.TokenType, "access")
	}
}

func TestVerifyAccessToken_Expired(t *testing.T) {
	tok := makeAccessToken("1", "user@example.com", time.Now().Add(-time.Hour))
	_, err := verifyAccessToken(tok)
	if err == nil {
		t.Fatal("expected error for expired token")
	}
}

func TestVerifyAccessToken_WrongSecret(t *testing.T) {
	claims := jwtClaims{
		Email:     "user@example.com",
		TokenType: "access",
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "1",
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	s, _ := token.SignedString([]byte("wrong-secret"))
	_, err := verifyAccessToken(s)
	if err == nil {
		t.Fatal("expected error for wrong secret")
	}
}

func TestVerifyAccessToken_RefreshTokenRejected(t *testing.T) {
	tok := makeRefreshToken("1", time.Now().Add(time.Hour))
	_, err := verifyAccessToken(tok)
	if err == nil {
		t.Fatal("expected error: refresh token should not be accepted as access")
	}
	if err.Error() != "not an access token" {
		t.Errorf("error = %q, want %q", err.Error(), "not an access token")
	}
}

func TestVerifyAccessToken_GarbageString(t *testing.T) {
	_, err := verifyAccessToken("not-a-jwt")
	if err == nil {
		t.Fatal("expected error for garbage input")
	}
}

func TestVerifyAccessToken_EmptyString(t *testing.T) {
	_, err := verifyAccessToken("")
	if err == nil {
		t.Fatal("expected error for empty input")
	}
}

// ─── jwtMiddleware ────────────────────────────────────────────────────────────

func TestJwtMiddleware_ValidToken(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	handler := jwtMiddleware(inner)

	tok := makeAccessToken("1", "user@example.com", time.Now().Add(time.Hour))
	req := httptest.NewRequest("GET", "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusOK)
	}
}

func TestJwtMiddleware_NoToken(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := jwtMiddleware(inner)

	req := httptest.NewRequest("GET", "/protected", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusUnauthorized)
	}
}

func TestJwtMiddleware_InvalidToken(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := jwtMiddleware(inner)

	req := httptest.NewRequest("GET", "/protected", nil)
	req.Header.Set("Authorization", "Bearer invalid-token")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusUnauthorized)
	}
}

func TestJwtMiddleware_ExemptPath(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	handler := jwtMiddleware(inner, "/health", "/metrics")

	req := httptest.NewRequest("GET", "/health", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusOK)
	}
}

func TestJwtMiddleware_OptionsPassed(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := jwtMiddleware(inner)

	req := httptest.NewRequest("OPTIONS", "/protected", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", rr.Code, http.StatusOK)
	}
}
