"""Outbox processor — publishes pending events to Kafka.

Runs as a background thread. Polls the OutboxMessage table for unpublished
events, publishes them to Kafka, and marks them as published.

Redis publishing happens immediately in commands.py for real-time sync.
The outbox only handles Kafka delivery (for audit logging).
"""

import json
import logging
import os
import time

from kafka import KafkaProducer

logger = logging.getLogger(__name__)

_kafka_producer = None


def _get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is not None:
        return _kafka_producer
    addr = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
    if not addr:
        return None
    try:
        _kafka_producer = KafkaProducer(
            bootstrap_servers=[addr],
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )
        return _kafka_producer
    except Exception:
        logger.exception("Failed to create Kafka producer")
        return None


def _publish_to_kafka(topic: str, payload: dict):
    """Publish event to Kafka for audit service."""
    producer = _get_kafka_producer()
    if producer is None:
        return False
    try:
        producer.send(topic, payload)
        producer.flush(timeout=5)
        return True
    except Exception:
        logger.exception("Failed to publish to Kafka")
        return False


def process_outbox(batch_size: int = 10):
    """Process pending outbox messages. Called periodically by the worker.

    Returns the number of messages successfully published.
    """
    from .models import OutboxMessage

    messages = OutboxMessage.objects.filter(published=False)[:batch_size]
    published_count = 0

    for msg in messages:
        topic = _topic_for_event(msg.event_type)

        # Build payload for Kafka
        payload = {
            "event": msg.event_type,
            "aggregate_type": msg.aggregate_type,
            "aggregate_id": msg.aggregate_id,
            "timestamp": msg.created_at.replace(microsecond=0).isoformat() + "Z",
            **msg.payload,
        }

        kafka_ok = _publish_to_kafka(topic, payload) if topic else True

        if kafka_ok:
            msg.published = True
            msg.save(update_fields=["published"])
            published_count += 1

    return published_count


def _topic_for_event(event_type: str) -> str | None:
    """Map event type to Kafka topic."""
    mapping = {
        "document.updated": "document.events",
    }
    return mapping.get(event_type)


def run_forever(poll_interval: int = 5, batch_size: int = 10):
    """Run the outbox processor loop. Blocks forever.

    Args:
        poll_interval: Seconds between polls.
        batch_size: Max events to process per batch.
    """
    logger.info("Outbox processor started (interval=%ds, batch=%d)", poll_interval, batch_size)
    while True:
        try:
            count = process_outbox(batch_size)
            if count:
                logger.info("Published %d outbox messages to Kafka", count)
        except Exception:
            logger.exception("Outbox processor error")
        time.sleep(poll_interval)
