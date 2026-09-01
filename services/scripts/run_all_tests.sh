#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_all_tests.sh — Run tests for all services
#
# Usage:
#   ./scripts/run_all_tests.sh              # Run all services
#   ./scripts/run_all_tests.sh gateway      # Run only gateway tests
#   ./scripts/run_all_tests.sh frontend     # Run only frontend tests
#   ./scripts/run_all_tests.sh auth         # Run only auth service tests
#   ./scripts/run_all_tests.sh audit        # Run only audit service tests
#   ./scripts/run_all_tests.sh export       # Run only export service tests
#   ./scripts/run_all_tests.sh document     # Run only document service tests
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICES_DIR="$PROJECT_ROOT/services"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0
RESULTS=()

run_test() {
    local name="$1"
    local script="$2"
    local container="$3"

    echo -e "\n${YELLOW}━━━ Running: ${name} ━━━${NC}"

    if [ -n "$container" ]; then
        # Run inside Docker container
        docker compose exec -T "$container" bash "$script" 2>&1
    else
        # Run locally (gateway uses docker build --target test)
        bash "$script" 2>&1
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ ${name} passed${NC}"
        PASSED=$((PASSED + 1))
        RESULTS+=("✓ ${name}")
    else
        echo -e "${RED}✗ ${name} failed${NC}"
        FAILED=$((FAILED + 1))
        RESULTS+=("✗ ${name}")
    fi
}

echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Test Runner — All Services${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"

TARGET="${1:-all}"

# ── Gateway (Go — runs via Docker build) ──────────────────────────────────────
if [[ "$TARGET" == "all" || "$TARGET" == "gateway" ]]; then
    echo -e "\n${YELLOW}━━━ Building & testing Gateway (Go) ━━━${NC}"
    cd "$SERVICES_DIR/gateway"
    docker build --target test -t gateway-test . 2>&1 | tail -50
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Gateway tests passed${NC}"
        PASSED=$((PASSED + 1))
        RESULTS+=("✓ Gateway (Go)")
    else
        echo -e "${RED}✗ Gateway tests failed${NC}"
        FAILED=$((FAILED + 1))
        RESULTS+=("✗ Gateway (Go)")
    fi
    cd "$PROJECT_ROOT"
fi

# ── Frontend (Jest — runs inside container) ───────────────────────────────────
if [[ "$TARGET" == "all" || "$TARGET" == "frontend" ]]; then
    run_test "Frontend (Jest)" "/app/scripts/run_frontend_tests.sh" "frontend"
fi

# ── Auth Service (pytest — runs inside container) ─────────────────────────────
if [[ "$TARGET" == "all" || "$TARGET" == "auth" ]]; then
    run_test "Auth Service (pytest)" "/app/scripts/run_auth_tests.sh" "auth-service"
fi

# ── Audit Service (pytest — runs inside container) ────────────────────────────
if [[ "$TARGET" == "all" || "$TARGET" == "audit" ]]; then
    run_test "Audit Service (pytest)" "/app/scripts/run_audit_tests.sh" "audit-service"
fi

# ── Export Service (pytest — runs inside container) ───────────────────────────
if [[ "$TARGET" == "all" || "$TARGET" == "export" ]]; then
    run_test "Export Service (pytest)" "/app/scripts/run_export_tests.sh" "export-service"
fi

# ── Document Service (Django — runs inside container) ─────────────────────────
if [[ "$TARGET" == "all" || "$TARGET" == "document" ]]; then
    run_test "Document Service (Django)" "/app/scripts/run_document_tests.sh" "document-service"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Results${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
TOTAL=$((PASSED + FAILED))
echo -e "  Total: ${TOTAL}  ${GREEN}Passed: ${PASSED}${NC}  ${RED}Failed: ${FAILED}${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"

if [ $FAILED -gt 0 ]; then
    exit 1
fi
