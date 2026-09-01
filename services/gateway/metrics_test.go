package main

import (
	"testing"
)

func TestMetricsIncrement(t *testing.T) {
	// Verify metrics can be incremented and decremented without panicking
	gatewayWsConnections.Inc()
	gatewayWsConnections.Dec()
	gatewayMessagesReceived.Inc()
	gatewayRedisPublishes.Inc()
	gatewayDocumentServiceRequests.Inc()
	gatewayDocumentServiceLatency.Observe(0.05)
}
