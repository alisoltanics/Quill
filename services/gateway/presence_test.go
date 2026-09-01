package main

import (
	"testing"
)

func TestPresenceKey(t *testing.T) {
	tests := []struct {
		docID int
		want  string
	}{
		{1, "doc:1:online"},
		{42, "doc:42:online"},
		{100, "doc:100:online"},
	}
	for _, tt := range tests {
		got := presenceKey(tt.docID)
		if got != tt.want {
			t.Errorf("presenceKey(%d) = %q, want %q", tt.docID, got, tt.want)
		}
	}
}
