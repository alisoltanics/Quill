"""Django management command to start the outbox processor.

Usage:
    python manage.py run_outbox_processor
"""

import logging

from django.core.management.base import BaseCommand

from api.outbox import run_forever

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start the outbox event processor (background worker)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval", type=int, default=5,
            help="Seconds between polls (default: 5)",
        )
        parser.add_argument(
            "--batch-size", type=int, default=10,
            help="Max events per batch (default: 10)",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        batch_size = options["batch_size"]
        self.stdout.write(
            f"Starting outbox processor (interval={interval}s, batch={batch_size})"
        )
        run_forever(poll_interval=interval, batch_size=batch_size)
