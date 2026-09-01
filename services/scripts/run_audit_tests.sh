#!/usr/bin/env bash
set -euo pipefail
echo "════════════════════════════════════════════════════════════"
echo "  Audit Service Tests"
echo "════════════════════════════════════════════════════════════"
cd /app
python -m pytest tests/test_audit.py -v --tb=short 2>&1
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All audit service tests passed"
echo "════════════════════════════════════════════════════════════"
