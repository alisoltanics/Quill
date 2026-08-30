package main

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    gatewayWsConnections = promauto.NewGauge(prometheus.GaugeOpts{
        Name: "gateway_ws_connections",
        Help: "Current number of active websocket clients.",
    })
    gatewayMessagesReceived = promauto.NewCounter(prometheus.CounterOpts{
        Name: "gateway_messages_received_total",
        Help: "Total messages received from websocket clients.",
    })
    gatewayRedisPublishes = promauto.NewCounter(prometheus.CounterOpts{
        Name: "gateway_redis_publishes_total",
        Help: "Total messages published to Redis.",
    })
    gatewayDocumentServiceRequests = promauto.NewCounter(prometheus.CounterOpts{
        Name: "gateway_document_service_requests_total",
        Help: "Total requests sent to the document service.",
    })
    gatewayDocumentServiceLatency = promauto.NewHistogram(prometheus.HistogramOpts{
        Name:    "gateway_document_service_request_duration_seconds",
        Help:    "Latency of document service requests in seconds.",
        Buckets: prometheus.DefBuckets,
    })
)
