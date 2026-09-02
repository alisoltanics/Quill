#!/bin/sh
set -e

HOST="${POSTGRES_HOST:-}"
PORT="${POSTGRES_PORT:-5432}"

if [ -n "$HOST" ]; then
  echo "Waiting for Postgres at $HOST:$PORT..."
  until python - <<'PY'
import os, sys, psycopg
host=os.environ.get('POSTGRES_HOST')
port=int(os.environ.get('POSTGRES_PORT','5432'))
user=os.environ.get('POSTGRES_USER','docuser')
db=os.environ.get('POSTGRES_DB','docdb')
pw=os.environ.get('POSTGRES_PASSWORD','docpass')
try:
    conn=psycopg.connect(host=host, port=port, user=user, dbname=db, password=pw, connect_timeout=2)
    conn.close()
    sys.exit(0)
except Exception as e:
    print('db not ready:', e)
    sys.exit(1)
PY
  do
    sleep 1
  done
fi

echo "Running migrations and starting server"
python manage.py migrate --noinput || true

# Start outbox processor in background
python manage.py run_outbox_processor --interval 5 --batch-size 10 &

exec python manage.py runserver 0.0.0.0:8000
