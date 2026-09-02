#!/bin/sh
# Start both the Django server and the outbox processor

# Run migrations
python manage.py migrate --noinput

# Start outbox processor in background
python manage.py run_outbox_processor --interval 5 --batch-size 10 &

# Start Django server in foreground
python manage.py runserver 0.0.0.0:8000
