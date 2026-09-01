package main

import (
	"errors"
	"net/http"
	"os"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

// jwtSecret is read once at startup. Set via JWT_SECRET env var.
var jwtSecret = func() []byte {
	s := os.Getenv("JWT_SECRET")
	if s == "" {
		s = "change-me-in-production"
	}
	return []byte(s)
}()

type jwtClaims struct {
	Email    string `json:"email"`
	TokenType string `json:"type"`
	jwt.RegisteredClaims
}

// extractToken pulls the Bearer token from the Authorization header.
// For WebSocket connections (where browsers cannot set headers) it also
// accepts a ?token=<jwt> query parameter.
func extractToken(r *http.Request) (string, error) {
	if authHeader := r.Header.Get("Authorization"); authHeader != "" {
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) == 2 && strings.EqualFold(parts[0], "bearer") {
			return parts[1], nil
		}
		return "", errors.New("malformed Authorization header")
	}
	if tok := r.URL.Query().Get("token"); tok != "" {
		return tok, nil
	}
	return "", errors.New("no token provided")
}

// verifyAccessToken parses and validates a JWT access token.
func verifyAccessToken(tokenStr string) (*jwtClaims, error) {
	claims := &jwtClaims{}
	token, err := jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, errors.New("unexpected signing method")
		}
		return jwtSecret, nil
	})
	if err != nil || !token.Valid {
		return nil, errors.New("invalid or expired token")
	}
	if claims.TokenType != "access" {
		return nil, errors.New("not an access token")
	}
	return claims, nil
}

// jwtMiddleware wraps a handler and rejects requests that lack a valid
// Bearer token. Paths listed in exempt are allowed through without a token
// (used for /health, /metrics). OPTIONS preflight requests are always passed.
func jwtMiddleware(next http.Handler, exempt ...string) http.Handler {
	exemptSet := make(map[string]struct{}, len(exempt))
	for _, p := range exempt {
		exemptSet[p] = struct{}{}
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Always allow CORS preflight
		if r.Method == http.MethodOptions {
			next.ServeHTTP(w, r)
			return
		}
		if _, ok := exemptSet[r.URL.Path]; ok {
			next.ServeHTTP(w, r)
			return
		}

		tokenStr, err := extractToken(r)
		if err != nil {
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Content-Type", "application/json")
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		if _, err := verifyAccessToken(tokenStr); err != nil {
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Content-Type", "application/json")
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}

		next.ServeHTTP(w, r)
	})
}
