from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

registry = CollectorRegistry(auto_describe=True)

REQUEST_COUNT = Counter(
    'document_service_http_requests_total',
    'Total number of HTTP requests handled by the document service.',
    ['method', 'path', 'status'],
    registry=registry,
)

REQUEST_LATENCY = Histogram(
    'document_service_http_request_duration_seconds',
    'HTTP request latency in seconds for the document service.',
    ['method', 'path'],
    registry=registry,
)

DOCUMENT_SAVE_COUNT = Counter(
    'document_service_document_saves_total',
    'Total number of document saves.',
    ['mode'],
    registry=registry,
)

DOCUMENT_SAVE_ERRORS = Counter(
    'document_service_document_save_errors_total',
    'Total number of document save errors.',
    registry=registry,
)

REDIS_PUBLISH_COUNT = Counter(
    'document_service_redis_publishes_total',
    'Total number of Redis publishes triggered by the service.',
    registry=registry,
)


def get_metrics_payload():
    return generate_latest(registry)
