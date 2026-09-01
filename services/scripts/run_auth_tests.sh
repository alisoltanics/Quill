#!/usr/bin/env bash
set -euo pipefail
echo "════════════════════════════════════════════════════════════"
echo "  Auth Service Tests"
echo "════════════════════════════════════════════════════════════"
cd /app
python -m pytest tests/test_auth.py -v --tb=short 2>&1
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All auth service tests passed"
echo "════════════════════════════════════════════════════════════"
