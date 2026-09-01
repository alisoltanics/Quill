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
from .models import Document, DocumentPermission, DocumentVersion, Folder
from .serializers import (
    DocumentCreateSerializer,
    DocumentDetailSerializer,
    DocumentPermissionSerializer,
    DocumentSerializer,
    DocumentUpdateSerializer,
    FolderCreateSerializer,
    FolderDetailSerializer,
    FolderSerializer,
    PermissionUpdateSerializer,
    ShareCreateSerializer,
    SharedWithMeSerializer,
)

logger = logging.getLogger(__name__)
_JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
_kafka_producer = None
_UNSET = object()  # sentinel to distinguish "not provided" from None


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


def _user_email(request) -> str:
    return request.user.get("email", "")


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
        return JsonResponse({"folders": FolderSerializer(folders, many=True).data})

    def post(self, request):
        serializer = FolderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        folder = Folder.objects.create(user_id=_uid(request), **serializer.validated_data)
        return JsonResponse(FolderSerializer(folder).data, status=201)


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
        serializer = FolderSerializer(folder, data=request.data, partial=True)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        serializer.save()
        return JsonResponse(FolderSerializer(folder).data)

    def delete(self, request, pk):
        folder = self._get(request, pk)
        if folder is None:
            return JsonResponse({"error": "not found"}, status=404)
        folder.delete()
        return JsonResponse({"deleted": pk})


# ─── Document views ────────────────────────────────────────────────────────────

class DocumentListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = _uid(request)
        folders = Folder.objects.filter(user_id=uid).prefetch_related("documents")
        root_docs = Document.objects.filter(user_id=uid, folder__isnull=True)

        return JsonResponse({
            "folders": FolderDetailSerializer(folders, many=True).data,
            "documents": DocumentSerializer(root_docs, many=True).data,
        })

    def post(self, request):
        serializer = DocumentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        data = serializer.validated_data
        folder_id = data.pop("folder_id", None)
        folder = None
        if folder_id:
            try:
                folder = Folder.objects.get(pk=folder_id, user_id=_uid(request))
            except Folder.DoesNotExist:
                return JsonResponse({"error": "folder not found"}, status=404)
        doc = Document.objects.create(user_id=_uid(request), folder=folder, **data)
        return JsonResponse(DocumentSerializer(doc).data, status=201)


class DocumentDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_doc(self, request, pk):
        """Return the document if the user has at least viewer access."""
        uid = _uid(request)
        email = _user_email(request)
        try:
            doc = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return None
        # Owner always has access
        if doc.user_id == uid:
            return doc
        # Check permission table by email
        if _has_access(pk, email, "viewer"):
            return doc
        return None

    def get(self, request, pk):
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)
        return JsonResponse(DocumentDetailSerializer(doc).data)

    def patch(self, request, pk):
        started = time.time()
        uid = _uid(request)
        email = _user_email(request)

        # Need at least editor role to modify
        is_owner = Document.objects.filter(pk=pk, user_id=uid).exists()
        if not is_owner and not _has_access(pk, email, "editor"):
            _record(request, "403", started)
            return JsonResponse({"error": "forbidden"}, status=403)

        try:
            doc = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            _record(request, "404", started)
            return JsonResponse({"error": "not found"}, status=404)

        serializer = DocumentUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        data = serializer.validated_data

        # Resolve aliases
        title = data.get("title")
        folder_id = data.get("folder_id", _UNSET)
        content = data.get("content", _UNSET)
        yjs_state = data.get("yjs_state") or data.get("yjsState")
        full_replace = data.get("full", True)
        client_id = data.get("client_id") or data.get("clientId")

        if title is not None:
            doc.title = title

        # Move to a different folder (or root) — only owner can move
        if folder_id is not _UNSET:
            if not is_owner:
                _record(request, "403", started)
                return JsonResponse({"error": "forbidden"}, status=403)
            if folder_id is None:
                doc.folder = None
            else:
                try:
                    doc.folder = Folder.objects.get(pk=folder_id, user_id=_uid(request))
                except Folder.DoesNotExist:
                    return JsonResponse({"error": "folder not found"}, status=404)

        has_content = content is not _UNSET
        has_yjs = yjs_state is not None
        if has_content:
            text = str(content)
            doc.content = text if full_replace else (f"{doc.content}\n{text}" if doc.content else text)
        if has_yjs:
            doc.yjs_state = str(yjs_state)

        if has_content or has_yjs:
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
        return JsonResponse(DocumentSerializer(doc).data)

    def delete(self, request, pk):
        started = time.time()
        # Only owner can delete
        doc = Document.objects.filter(pk=pk, user_id=_uid(request)).first()
        if doc is None:
            _record(request, "404", started)
            return JsonResponse({"error": "not found"}, status=404)
        doc.delete()
        _record(request, "200", started)
        return JsonResponse({"deleted": pk})


# ─── Sharing helpers ──────────────────────────────────────────────────────────

def _get_user_role(doc_id: int, user_email: str) -> str | None:
    """Return the role string for *user_email* on *doc_id*, or None."""
    perm = (
        DocumentPermission.objects
        .filter(document_id=doc_id, user_email=user_email)
        .values_list("role", flat=True)
        .first()
    )
    return perm


def _has_access(doc_id: int, user_email: str, minimum: str = "viewer", user_id: int | None = None) -> bool:
    """Check whether *user_email* has at least *minimum* role on the document.

    The document owner (matched by *user_id* against ``Document.user_id``) is
    always considered to have the ``owner`` role even if no ``DocumentPermission``
    record exists.
    """
    hierarchy = {"viewer": 0, "editor": 1, "owner": 2}
    role = _get_user_role(doc_id, user_email)
    if role is None and user_id is not None:
        try:
            doc = Document.objects.get(pk=doc_id, user_id=user_id)
            role = DocumentPermission.ROLE_OWNER
        except Document.DoesNotExist:
            pass
    if role is None:
        return False
    return hierarchy.get(role, -1) >= hierarchy.get(minimum, -1)




# ─── Sharing views ────────────────────────────────────────────────────────────

class DocumentShareView(APIView):
    """Share a document with another user or list existing permissions.

    POST  /api/documents/<id>/share   — grant access
    GET   /api/documents/<id>/permissions — list all collaborators
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_doc(self, request, pk):
        """Return the document if the user is the owner."""
        try:
            return Document.objects.get(pk=pk, user_id=_uid(request))
        except Document.DoesNotExist:
            return None

    def post(self, request, pk):
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)

        serializer = ShareCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        target_email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        # Cannot share with yourself
        if target_email == _user_email(request):
            return JsonResponse({"error": "cannot share with yourself"}, status=400)

        perm, created = DocumentPermission.objects.update_or_create(
            document=doc,
            user_email=target_email,
            defaults={
                "role": role,
                "granted_by": _user_email(request),
            },
        )
        return JsonResponse(
            DocumentPermissionSerializer(perm).data,
            status=201 if created else 200,
        )

    def get(self, request, pk):
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)

        perms = DocumentPermission.objects.filter(document=doc)
        return JsonResponse({"permissions": DocumentPermissionSerializer(perms, many=True).data})


class DocumentPermissionDetailView(APIView):
    """Update or revoke a specific user's permission.

    PATCH  /api/documents/<id>/permissions/<email>  — change role
    DELETE /api/documents/<id>/permissions/<email>  — revoke access
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, user_email):
        # Only the owner can modify permissions
        if not _has_access(pk, _user_email(request), "owner", user_id=_uid(request)):
            return JsonResponse({"error": "forbidden"}, status=403)

        serializer = PermissionUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        role = serializer.validated_data["role"]

        try:
            perm = DocumentPermission.objects.get(document_id=pk, user_email=user_email)
        except DocumentPermission.DoesNotExist:
            return JsonResponse({"error": "permission not found"}, status=404)

        # Cannot remove the last owner
        if perm.role == DocumentPermission.ROLE_OWNER and role != DocumentPermission.ROLE_OWNER:
            owner_count = DocumentPermission.objects.filter(
                document_id=pk, role=DocumentPermission.ROLE_OWNER
            ).count()
            if owner_count <= 1:
                return JsonResponse({"error": "cannot remove the last owner"}, status=400)

        perm.role = role
        perm.save(update_fields=["role", "updated_at"])
        return JsonResponse(DocumentPermissionSerializer(perm).data)

    def delete(self, request, pk, user_email):
        # Only the owner can revoke permissions
        if not _has_access(pk, _user_email(request), "owner", user_id=_uid(request)):
            return JsonResponse({"error": "forbidden"}, status=403)

        try:
            perm = DocumentPermission.objects.get(document_id=pk, user_email=user_email)
        except DocumentPermission.DoesNotExist:
            return JsonResponse({"error": "permission not found"}, status=404)

        # Cannot remove the last owner
        if perm.role == DocumentPermission.ROLE_OWNER:
            owner_count = DocumentPermission.objects.filter(
                document_id=pk, role=DocumentPermission.ROLE_OWNER
            ).count()
            if owner_count <= 1:
                return JsonResponse({"error": "cannot remove the last owner"}, status=400)

        perm.delete()
        return JsonResponse({"deleted": user_email})


class SharedWithMeView(APIView):
    """List documents that other users have shared with the current user.

    GET /api/shared-with-me
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        email = _user_email(request)
        perm_ids = (
            DocumentPermission.objects
            .filter(user_email=email)
            .exclude(role=DocumentPermission.ROLE_OWNER)
            .values_list("document_id", flat=True)
        )
        docs = Document.objects.filter(pk__in=perm_ids)
        result = []
        for doc in docs:
            perm = DocumentPermission.objects.filter(document_id=doc.pk, user_email=email).first()
            doc._shared_role = perm.role if perm else None
            doc._shared_granted_by = perm.granted_by if perm else None
            result.append(doc)
        return JsonResponse({"documents": SharedWithMeSerializer(result, many=True).data})
