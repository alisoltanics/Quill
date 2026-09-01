#!/usr/bin/env bash
set -euo pipefail
echo "════════════════════════════════════════════════════════════"
echo "  Document Service Tests"
echo "════════════════════════════════════════════════════════════"
cd /app
python manage.py test tests.test_api --verbosity=2 --no-input 2>&1
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  All document service tests passed"
echo "════════════════════════════════════════════════════════════"
