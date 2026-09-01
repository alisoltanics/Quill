import json
import logging
import os
import time
from datetime import datetime

import jwt
import redis
from kafka import KafkaProducer
from django.http import HttpResponse, JsonResponse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .metrics import (
    CONTENT_TYPE_LATEST,
    DOCUMENT_SAVE_COUNT,
    DOCUMENT_SAVE_ERRORS,
    REDIS_PUBLISH_COUNT,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    get_metrics_payload,
)
from .models import Document, DocumentVersion, Folder

logger = logging.getLogger(__name__)
_JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
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


def _publish_kafka(doc: Document, request, client_id: str | None, version: int, action: str = "updated"):
    producer = _get_kafka_producer()
    if producer is None:
        return

    user_id = _uid(request)
    username = (
        request.user.get("name")
        or request.user.get("preferred_username")
        or request.user.get("username")
        or f"user-{user_id}"
    )

    payload = {
        "event": "document.updated",
        "document_id": doc.pk,
        "user_id": user_id,
        "version": version,
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "client_id": client_id or "",
        "action": action,
        "user": username,
    }

    try:
        producer.send("document.events", payload)
        producer.flush(timeout=5)
    except Exception:
        logger.exception("Failed to publish Kafka event")


# ─── JWT auth ──────────────────────────────────────────────────────────────────

class _JWTUser:
    is_authenticated = True

    def __init__(self, payload):
        self._payload = payload

    def __getitem__(self, key):
        return self._payload[key]

    def get(self, key, default=None):
        return self._payload.get(key, default)


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        try:
            payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
            if payload.get("type") != "access":
                raise AuthenticationFailed("Not an access token")
            return (_JWTUser(payload), token)
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token")


def _uid(request) -> int:
    return int(request.user["sub"])


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _publish(doc: Document):
    if not doc.yjs_state:
        return
    addr = os.environ.get("REDIS_ADDR")
    if not addr:
        return
    try:
        r = redis.Redis.from_url(f"redis://{addr}")
        r.publish(
            "gateway:events",
            json.dumps({
                "type": "sync-state",
                "docId": doc.pk,
                "clientId": "document-service",
                "update": doc.yjs_state,
            }),
        )
        REDIS_PUBLISH_COUNT.inc()
    except redis.RedisError:
        logger.warning("Redis publish failed", exc_info=True)


def _record(request, status, started):
    lbl = {"method": request.method, "path": request.path}
    REQUEST_COUNT.labels(**lbl, status=status).inc()
    REQUEST_LATENCY.labels(**lbl).observe(time.time() - started)


def _doc_json(doc: Document) -> dict:
    return {
        "id": doc.pk,
        "folder_id": doc.folder_id,
        "title": doc.title,
        "content": doc.content,
        "yjs_state": doc.yjs_state,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


def _folder_json(folder: Folder) -> dict:
    return {
        "id": folder.pk,
        "name": folder.name,
        "created_at": folder.created_at.isoformat(),
        "updated_at": folder.updated_at.isoformat(),
    }


_AUTH = {"authentication_classes": [JWTAuthentication], "permission_classes": [IsAuthenticated]}


# ─── Health / Metrics ──────────────────────────────────────────────────────────

class HealthView(APIView):
    def get(self, request):
        return JsonResponse({"status": "ok"})


def metrics_view(request):
    return HttpResponse(get_metrics_payload(), content_type=CONTENT_TYPE_LATEST)


# ─── Folder views ──────────────────────────────────────────────────────────────

class FolderListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        folders = Folder.objects.filter(user_id=_uid(request))
        return JsonResponse({"folders": [_folder_json(f) for f in folders]})

    def post(self, request):
        name = (request.data or {}).get("name", "New Folder")
        folder = Folder.objects.create(user_id=_uid(request), name=str(name))
        return JsonResponse(_folder_json(folder), status=201)


class FolderDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        try:
            return Folder.objects.get(pk=pk, user_id=_uid(request))
        except Folder.DoesNotExist:
            return None

    def patch(self, request, pk):
        folder = self._get(request, pk)
        if folder is None:
            return JsonResponse({"error": "not found"}, status=404)
        name = (request.data or {}).get("name")
        if name:
            folder.name = str(name)
            folder.save()
        return JsonResponse(_folder_json(folder))

    def delete(self, request, pk):
        folder = self._get(request, pk)
        if folder is None:
            return JsonResponse({"error": "not found"}, status=404)
        # Unlink documents from folder (SET_NULL) then delete folder
        folder.delete()
        return JsonResponse({"deleted": pk})


# ─── Document views ────────────────────────────────────────────────────────────

class DocumentListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Return folders with their docs + root-level docs in one call
        uid = _uid(request)
        folders = Folder.objects.filter(user_id=uid).prefetch_related("documents")
        root_docs = Document.objects.filter(user_id=uid, folder__isnull=True)
        return JsonResponse({
            "folders": [
                {**_folder_json(f), "documents": [_doc_json(d) for d in f.documents.all()]}
                for f in folders
            ],
            "documents": [_doc_json(d) for d in root_docs],
        })

    def post(self, request):
        payload = request.data or {}
        title = payload.get("title", "Untitled")
        folder_id = payload.get("folder_id")
        folder = None
        if folder_id:
            try:
                folder = Folder.objects.get(pk=folder_id, user_id=_uid(request))
            except Folder.DoesNotExist:
                return JsonResponse({"error": "folder not found"}, status=404)
        doc = Document.objects.create(user_id=_uid(request), title=str(title), folder=folder)
        return JsonResponse(_doc_json(doc), status=201)


class DocumentDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_doc(self, request, pk):
        try:
            return Document.objects.get(pk=pk, user_id=_uid(request))
        except Document.DoesNotExist:
            return None

    def get(self, request, pk):
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)
        versions = [
            {
                "id": v.pk,
                "client_id": v.client_id,
                "yjs_state": v.yjs_state,
                "created_at": v.created_at.isoformat(),
            }
            for v in doc.versions.order_by("-created_at")[:20]
        ]
        data = _doc_json(doc)
        data["versions"] = versions
        return JsonResponse(data)

    def patch(self, request, pk):
        started = time.time()
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)

        payload = request.data or {}
        if "title" in payload:
            doc.title = str(payload["title"])

        # Move to a different folder (or root)
        if "folder_id" in payload:
            fid = payload["folder_id"]
            if fid is None:
                doc.folder = None
            else:
                try:
                    doc.folder = Folder.objects.get(pk=fid, user_id=_uid(request))
                except Folder.DoesNotExist:
                    return JsonResponse({"error": "folder not found"}, status=404)

        full_replace = bool(payload.get("full", True))
        if "content" in payload:
            text = str(payload["content"])
            doc.content = text if full_replace else (f"{doc.content}\n{text}" if doc.content else text)
        if "yjs_state" in payload or "yjsState" in payload:
            doc.yjs_state = str(payload.get("yjs_state") or payload.get("yjsState") or "")

        if "content" in payload or "yjs_state" in payload or "yjsState" in payload:
            client_id = payload.get("clientId") or payload.get("client_id")
            try:
                doc.save()
                DOCUMENT_SAVE_COUNT.labels(mode="full" if full_replace else "append").inc()
            except Exception:
                logger.exception("Failed to save document")
                DOCUMENT_SAVE_ERRORS.inc()
                _record(request, "500", started)
                return JsonResponse({"error": "save failed"}, status=500)
            version = DocumentVersion.objects.create(
                document=doc,
                content=doc.content,
                yjs_state=doc.yjs_state,
                client_id=client_id,
            )
            _publish(doc)
            _publish_kafka(doc, request, client_id, version.pk)
        else:
            doc.save()

        _record(request, "200", started)
        return JsonResponse(_doc_json(doc))

    def delete(self, request, pk):
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)
        doc.delete()
        return JsonResponse({"deleted": pk})
