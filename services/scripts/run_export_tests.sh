#!/usr/bin/env bash
set -euo pipefail
echo "════════════════════════════════════════════════════════════"
echo "  Export Service Tests"
echo "════════════════════════════════════════════════════════════"
cd /app
python -m pytest tests/test_export.py -v --tb=short 2>&1
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All export service tests passed"
echo "════════════════════════════════════════════════════════════"
