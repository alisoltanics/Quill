"""Commands — write operations for the Document service.

Each command encapsulates a single state-changing operation. Commands are
responsible for:
- Validating input
- Persisting changes to the write database
- Creating version snapshots
- Publishing side effects (Redis, Kafka)

Commands return the affected model instance (or None on failure).
"""

import logging
from datetime import datetime

import redis
from kafka import KafkaProducer

from .models import Document, DocumentPermission, DocumentVersion, Folder

logger = logging.getLogger(__name__)

# Sentinel shared between commands and views
UNSET = object()

_kafka_producer = None


def _get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is not None:
        return _kafka_producer
    import os
    addr = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
    if not addr:
        return None
    try:
        _kafka_producer = KafkaProducer(
            bootstrap_servers=[addr],
            value_serializer=lambda value: __import__("json").dumps(value).encode("utf-8"),
        )
        return _kafka_producer
    except Exception:
        logger.exception("Failed to create Kafka producer")
        return None


def _publish_redis(doc: Document):
    import os
    if not doc.yjs_state:
        return
    addr = os.environ.get("REDIS_ADDR")
    if not addr:
        return
    try:
        r = redis.Redis.from_url(f"redis://{addr}")
        r.publish(
            "gateway:events",
            __import__("json").dumps({
                "type": "sync-state",
                "docId": doc.pk,
                "clientId": "document-service",
                "update": doc.yjs_state,
            }),
        )
    except redis.RedisError:
        logger.warning("Redis publish failed", exc_info=True)


def _publish_kafka(doc: Document, user_id: int, client_id: str | None, version: int, action: str = "updated"):
    producer = _get_kafka_producer()
    if producer is None:
        return
    payload = {
        "event": "document.updated",
        "document_id": doc.pk,
        "user_id": user_id,
        "version": version,
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "client_id": client_id or "",
        "action": action,
    }
    try:
        producer.send("document.events", payload)
        producer.flush(timeout=5)
    except Exception:
        logger.exception("Failed to publish Kafka event")


# ─── Folder Commands ────────────────────────────────────────────────────────


def create_folder(user_id: int, name: str, idempotency_key: str | None = None) -> tuple[Folder, bool]:
    """Create a folder. Supports idempotent creation via idempotency_key.
    Returns (folder, created).
    """
    if idempotency_key is not None:
        folder, created = Folder.objects.get_or_create(
            user_id=user_id,
            idempotency_key=idempotency_key,
            defaults={"name": name},
        )
        return folder, created
    return Folder.objects.create(user_id=user_id, name=name), True


def update_folder(folder_id: int, user_id: int, data: dict) -> Folder | None:
    """Update folder fields. Returns None if not found."""
    try:
        folder = Folder.objects.get(pk=folder_id, user_id=user_id)
    except Folder.DoesNotExist:
        return None
    for field, value in data.items():
        setattr(folder, field, value)
    folder.save()
    return folder


def delete_folder(folder_id: int, user_id: int) -> bool:
    """Delete a folder. Returns True if deleted."""
    try:
        folder = Folder.objects.get(pk=folder_id, user_id=user_id)
    except Folder.DoesNotExist:
        return False
    folder.delete()
    return True


# ─── Document Commands ──────────────────────────────────────────────────────


def create_document(user_id: int, title: str, folder_id: int | None = None) -> Document:
    """Create a document, optionally in a folder."""
    folder = None
    if folder_id:
        folder = Folder.objects.get(pk=folder_id, user_id=user_id)
    return Document.objects.create(user_id=user_id, folder=folder, title=title)


def update_document(
    doc: Document,
    *,
    title: str | None = None,
    content: object = UNSET,
    yjs_state: str | None = None,
    folder_id: object = UNSET,
    full_replace: bool = True,
    client_id: str | None = None,
    user_id: int | None = None,
) -> Document:
    """Update a document. Creates a version snapshot if content changed.

    ``content`` and ``folder_id`` use UNSET to distinguish "not provided"
    from ``None`` (which means "move to root" for folder_id).
    """

    if title is not None:
        doc.title = title

    if folder_id is not UNSET:
        if folder_id is None:
            doc.folder = None
        else:
            doc.folder = Folder.objects.get(pk=folder_id, user_id=user_id)

    has_content = content is not UNSET
    has_yjs = yjs_state is not None

    if has_content:
        text = str(content)
        doc.content = text if full_replace else (f"{doc.content}\n{text}" if doc.content else text)
    if has_yjs:
        doc.yjs_state = str(yjs_state)

    if has_content or has_yjs:
        doc.save()
        version = DocumentVersion.objects.create(
            document=doc,
            content=doc.content,
            yjs_state=doc.yjs_state,
            client_id=client_id,
        )
        _publish_redis(doc)
        _publish_kafka(doc, user_id or doc.user_id, client_id, version.pk)
    else:
        doc.save()

    return doc


def delete_document(doc: Document) -> None:
    """Delete a document."""
    doc.delete()


# ─── Permission Commands ────────────────────────────────────────────────────


def share_document(
    doc: Document,
    target_email: str,
    role: str,
    granted_by: str,
) -> tuple[DocumentPermission, bool]:
    """Grant or update a permission on a document. Returns (perm, created)."""
    perm, created = DocumentPermission.objects.update_or_create(
        document=doc,
        user_email=target_email,
        defaults={"role": role, "granted_by": granted_by},
    )
    return perm, created


def update_permission(doc_id: int, user_email: str, role: str) -> DocumentPermission | None:
    """Update a user's role on a document."""
    try:
        perm = DocumentPermission.objects.get(document_id=doc_id, user_email=user_email)
    except DocumentPermission.DoesNotExist:
        return None
    perm.role = role
    perm.save(update_fields=["role", "updated_at"])
    return perm


def delete_permission(doc_id: int, user_email: str) -> bool:
    """Revoke a user's permission."""
    try:
        perm = DocumentPermission.objects.get(document_id=doc_id, user_email=user_email)
    except DocumentPermission.DoesNotExist:
        return False
    perm.delete()
    return True
