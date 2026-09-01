import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import List

from fastapi import Depends, FastAPI
from kafka import KafkaConsumer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import AuditActivity
from .schemas import ActivityItem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit_service")

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "document.events")
KAFKA_CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "audit-service")
DEBUG_MODE = os.environ.get("DEBUG", os.environ.get("AUDIT_DEBUG", "false")).lower() in ("1", "true", "yes")

app = FastAPI(title="Audit Service")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    Base.metadata.create_all(bind=engine)


def parse_timestamp(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


def process_event(event: dict) -> None:
    if event.get("event") != "document.updated":
        return

    document_id = int(event["document_id"])
    user_id = int(event["user_id"])
    version = int(event.get("version", 0))
    action = event.get("action", "updated")
    user_name = (
        event.get("user")
        or event.get("username")
        or f"user-{user_id}"
    )
    client_id = event.get("client_id")
    event_timestamp = parse_timestamp(event.get("timestamp", datetime.utcnow().isoformat() + "Z"))

    if DEBUG_MODE:
        logger.info(
            "Debug mode enabled, skipping audit DB persistence for document %s version %s",
            document_id,
            version,
        )
        return

    with SessionLocal() as db:
        audit = AuditActivity(
            document_id=document_id,
            user_id=user_id,
            user_name=user_name,
            action=action,
            version=version,
            client_id=client_id,
            event_timestamp=event_timestamp,
        )
        db.add(audit)
        db.commit()
        logger.info(
            "Audit stored event for document %s user %s version %s",
            document_id,
            user_name,
            version,
        )


def kafka_consumer_loop() -> None:
    while True:
        try:
            logger.info("Connecting to Kafka broker %s", KAFKA_BOOTSTRAP_SERVERS)
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
                group_id=KAFKA_CONSUMER_GROUP,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
            )

            for message in consumer:
                logger.info("Consumed Kafka message from topic %s partition %s offset %s", message.topic, message.partition, message.offset)
                try:
                    process_event(message.value)
                except Exception:
                    logger.exception("Failed to process Kafka message")
        except Exception:
            logger.exception("Kafka consumer crashed, retrying in 5 seconds")
            time.sleep(5)


@app.on_event("startup")
def startup_event() -> None:
    ensure_schema()
    thread = threading.Thread(target=kafka_consumer_loop, daemon=True)
    thread.start()
    logger.info("Started Kafka audit consumer thread")


@app.get("/api/documents/{document_id}/activity", response_model=List[ActivityItem])
def get_document_activity(document_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(AuditActivity)
        .where(AuditActivity.document_id == document_id)
        .order_by(AuditActivity.created_at.desc())
    )
    rows = db.scalars(stmt).all()
    return [
        ActivityItem(
            user=row.user_name,
            action=row.action,
            version=row.version,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]
