import logging
import os
import time

import jwt
from django.http import HttpResponse, JsonResponse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from . import commands, queries
from .commands import UNSET
from .metrics import (
    CONTENT_TYPE_LATEST,
    DOCUMENT_SAVE_COUNT,
    DOCUMENT_SAVE_ERRORS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    get_metrics_payload,
)
from .models import Document, DocumentPermission, Folder
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


def _uid(request) -> int:
    return int(request.user["sub"])


def _user_email(request) -> str:
    return request.user.get("email", "")


def _record(request, status, started):
    lbl = {"method": request.method, "path": request.path}
    REQUEST_COUNT.labels(**lbl, status=status).inc()
    REQUEST_LATENCY.labels(**lbl).observe(time.time() - started)


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


# ─── Health / Metrics ──────────────────────────────────────────────────────────

class HealthView(APIView):
    def get(self, request):
        return JsonResponse({"status": "ok"})


def metrics_view(request):
    return HttpResponse(get_metrics_payload(), content_type=CONTENT_TYPE_LATEST)


# ─── Folder views ──────────────────────────────────────────────────────────────

_IDEMPOTENCY_KEY_MAX_LEN = 255


def _idempotency_key(request) -> str | None:
    raw = request.headers.get("Idempotency-Key", "")
    key = raw.strip()
    if len(key) > _IDEMPOTENCY_KEY_MAX_LEN:
        raise ValueError("Idempotency-Key must be 255 characters or fewer")
    return key or None


class FolderListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # QUERY: read-only list
        data = queries.list_folders(_uid(request))
        return JsonResponse({"folders": data})

    def post(self, request):
        # COMMAND: create folder
        serializer = FolderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)

        uid = _uid(request)
        name = serializer.validated_data.get("name") or "New Folder"

        try:
            key = _idempotency_key(request)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        folder, created = commands.create_folder(uid, name, idempotency_key=key)
        return JsonResponse(FolderSerializer(folder).data, status=201 if created else 200)


class FolderDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        # COMMAND: update folder
        folder = commands.update_folder(pk, _uid(request), request.data)
        if folder is None:
            return JsonResponse({"error": "not found"}, status=404)
        return JsonResponse(FolderSerializer(folder).data)

    def delete(self, request, pk):
        # COMMAND: delete folder
        if not commands.delete_folder(pk, _uid(request)):
            return JsonResponse({"error": "not found"}, status=404)
        return JsonResponse({"deleted": pk})


# ─── Document views ────────────────────────────────────────────────────────────

class DocumentListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # QUERY: read-only list
        return JsonResponse(queries.list_documents(_uid(request)))

    def post(self, request):
        # COMMAND: create document
        serializer = DocumentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        data = serializer.validated_data
        folder_id = data.pop("folder_id", None)
        try:
            doc = commands.create_document(_uid(request), data.get("title", "Untitled"), folder_id)
        except Folder.DoesNotExist:
            return JsonResponse({"error": "folder not found"}, status=404)
        return JsonResponse(DocumentSerializer(doc).data, status=201)


class DocumentDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # QUERY: read-only access check + fetch
        doc = queries.can_access_document(pk, _uid(request), _user_email(request))
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)
        return JsonResponse(DocumentDetailSerializer(doc).data)

    def patch(self, request, pk):
        started = time.time()
        uid = _uid(request)
        email = _user_email(request)

        # Need at least editor role
        is_owner = Document.objects.filter(pk=pk, user_id=uid).exists()
        if not is_owner and not queries.has_access(pk, email, "editor"):
            _record(request, "403", started)
            return JsonResponse({"error": "forbidden"}, status=403)

        doc = queries.get_document(pk)
        if doc is None:
            _record(request, "404", started)
            return JsonResponse({"error": "not found"}, status=404)

        serializer = DocumentUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        data = serializer.validated_data

        # COMMAND: update document
        folder_id = data.get("folder_id", UNSET)
        if folder_id is not UNSET and not is_owner:
            _record(request, "403", started)
            return JsonResponse({"error": "forbidden"}, status=403)

        try:
            doc = commands.update_document(
                doc,
                title=data.get("title"),
                content=data.get("content", UNSET),
                yjs_state=data.get("yjs_state") or data.get("yjsState"),
                folder_id=folder_id,
                full_replace=data.get("full", True),
                client_id=data.get("client_id") or data.get("clientId"),
                user_id=uid,
            )
        except Folder.DoesNotExist:
            return JsonResponse({"error": "folder not found"}, status=404)
        except Exception:
            logger.exception("Failed to save document")
            DOCUMENT_SAVE_ERRORS.inc()
            _record(request, "500", started)
            return JsonResponse({"error": "save failed"}, status=500)

        DOCUMENT_SAVE_COUNT.labels(mode="full" if data.get("full", True) else "append").inc()
        _record(request, "200", started)
        return JsonResponse(DocumentSerializer(doc).data)

    def delete(self, request, pk):
        started = time.time()
        # COMMAND: delete document (owner only)
        doc = Document.objects.filter(pk=pk, user_id=_uid(request)).first()
        if doc is None:
            _record(request, "404", started)
            return JsonResponse({"error": "not found"}, status=404)
        commands.delete_document(doc)
        _record(request, "200", started)
        return JsonResponse({"deleted": pk})


# ─── Sharing views ────────────────────────────────────────────────────────────

class DocumentShareView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_doc(self, request, pk):
        try:
            return Document.objects.get(pk=pk, user_id=_uid(request))
        except Document.DoesNotExist:
            return None

    def post(self, request, pk):
        # COMMAND: share document
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)

        serializer = ShareCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        target_email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        if target_email == _user_email(request):
            return JsonResponse({"error": "cannot share with yourself"}, status=400)

        perm, created = commands.share_document(doc, target_email, role, _user_email(request))
        return JsonResponse(DocumentPermissionSerializer(perm).data, status=201 if created else 200)

    def get(self, request, pk):
        # QUERY: list permissions
        doc = self._get_doc(request, pk)
        if doc is None:
            return JsonResponse({"error": "not found"}, status=404)
        return JsonResponse({"permissions": queries.list_permissions(pk)})


class DocumentPermissionDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, user_email):
        # COMMAND: update permission
        if not queries.has_access(pk, _user_email(request), "owner", user_id=_uid(request)):
            return JsonResponse({"error": "forbidden"}, status=403)

        serializer = PermissionUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)
        role = serializer.validated_data["role"]

        # Cannot remove the last owner
        perm = queries.get_permission(pk, user_email)
        if perm is None:
            return JsonResponse({"error": "permission not found"}, status=404)

        if perm.role == DocumentPermission.ROLE_OWNER and role != DocumentPermission.ROLE_OWNER:
            if queries.count_owners(pk) <= 1:
                return JsonResponse({"error": "cannot remove the last owner"}, status=400)

        perm = commands.update_permission(pk, user_email, role)
        return JsonResponse(DocumentPermissionSerializer(perm).data)

    def delete(self, request, pk, user_email):
        # COMMAND: revoke permission
        if not queries.has_access(pk, _user_email(request), "owner", user_id=_uid(request)):
            return JsonResponse({"error": "forbidden"}, status=403)

        perm = queries.get_permission(pk, user_email)
        if perm is None:
            return JsonResponse({"error": "permission not found"}, status=404)

        if perm.role == DocumentPermission.ROLE_OWNER and queries.count_owners(pk) <= 1:
            return JsonResponse({"error": "cannot remove the last owner"}, status=400)

        commands.delete_permission(pk, user_email)
        return JsonResponse({"deleted": user_email})


class SharedWithMeView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # QUERY: list shared documents
        return JsonResponse({"documents": queries.list_shared_with_me(_user_email(request))})
