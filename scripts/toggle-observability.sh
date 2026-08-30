#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

value="${OBSERVABILITY_ENABLED:-false}"

if [ "$value" = "true" ] || [ "$value" = "True" ] || [ "$value" = "1" ]; then
  echo "Observability enabled: starting monitoring stack"
  docker compose up -d jaeger prometheus grafana redis-exporter postgres-exporter node-exporter
else
  echo "Observability disabled: stopping monitoring stack"
  docker compose stop jaeger prometheus grafana redis-exporter postgres-exporter node-exporter || true
fi
