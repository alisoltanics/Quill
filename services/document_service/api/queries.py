"""Queries — read operations for the Document service.

Queries are stateless read-only operations. They fetch data from the
read database (or cache) and return serialized results.

In a production CQRS setup, queries would hit a read replica or a
denormalized read model. Here we query the same database but keep
the read logic separate from write logic for clean separation.
"""

from .models import Document, DocumentPermission, DocumentVersion, Folder
from .serializers import (
    DocumentDetailSerializer,
    DocumentPermissionSerializer,
    DocumentSerializer,
    FolderDetailSerializer,
    FolderSerializer,
    SharedWithMeSerializer,
)


# ─── Folder Queries ─────────────────────────────────────────────────────────


def list_folders(user_id: int) -> list[dict]:
    """List all folders for a user."""
    folders = Folder.objects.filter(user_id=user_id)
    return FolderSerializer(folders, many=True).data


def get_folder(folder_id: int, user_id: int) -> Folder | None:
    """Get a single folder by ID, scoped to user."""
    try:
        return Folder.objects.get(pk=folder_id, user_id=user_id)
    except Folder.DoesNotExist:
        return None


# ─── Document Queries ───────────────────────────────────────────────────────


def list_documents(user_id: int) -> dict:
    """List folders (with nested docs) and root-level documents for a user."""
    folders = Folder.objects.filter(user_id=user_id).prefetch_related("documents")
    root_docs = Document.objects.filter(user_id=user_id, folder__isnull=True)
    return {
        "folders": FolderDetailSerializer(folders, many=True).data,
        "documents": DocumentSerializer(root_docs, many=True).data,
    }


def get_document(doc_id: int) -> Document | None:
    """Get a document with its 20 most recent versions."""
    try:
        return Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        return None


def get_document_with_versions(doc_id: int) -> dict | None:
    """Get a document serialized with its recent versions."""
    doc = get_document(doc_id)
    if doc is None:
        return None
    return DocumentDetailSerializer(doc).data


def has_access(doc_id: int, user_email: str, minimum: str = "viewer", user_id: int | None = None) -> bool:
    """Check whether user_email has at least *minimum* role on the document."""
    hierarchy = {"viewer": 0, "editor": 1, "owner": 2}
    role = _get_user_role(doc_id, user_email)
    if role is None and user_id is not None:
        try:
            Document.objects.get(pk=doc_id, user_id=user_id)
            role = DocumentPermission.ROLE_OWNER
        except Document.DoesNotExist:
            pass
    if role is None:
        return False
    return hierarchy.get(role, -1) >= hierarchy.get(minimum, -1)


def _get_user_role(doc_id: int, user_email: str) -> str | None:
    """Return the role string for user_email on doc_id, or None."""
    return (
        DocumentPermission.objects
        .filter(document_id=doc_id, user_email=user_email)
        .values_list("role", flat=True)
        .first()
    )


def can_access_document(doc_id: int, user_id: int, user_email: str) -> Document | None:
    """Return document if user has at least viewer access, else None."""
    doc = get_document(doc_id)
    if doc is None:
        return None
    if doc.user_id == user_id:
        return doc
    if has_access(doc_id, user_email, "viewer"):
        return doc
    return None


# ─── Permission Queries ─────────────────────────────────────────────────────


def list_permissions(doc_id: int) -> list[dict]:
    """List all permissions for a document."""
    perms = DocumentPermission.objects.filter(document_id=doc_id)
    return DocumentPermissionSerializer(perms, many=True).data


def get_permission(doc_id: int, user_email: str) -> DocumentPermission | None:
    """Get a single permission record."""
    try:
        return DocumentPermission.objects.get(document_id=doc_id, user_email=user_email)
    except DocumentPermission.DoesNotExist:
        return None


def count_owners(doc_id: int) -> int:
    """Count how many owners a document has."""
    return DocumentPermission.objects.filter(
        document_id=doc_id, role=DocumentPermission.ROLE_OWNER
    ).count()


# ─── Shared With Me ─────────────────────────────────────────────────────────


def list_shared_with_me(user_email: str) -> list[dict]:
    """List documents shared with the current user (excludes ownership)."""
    perm_ids = (
        DocumentPermission.objects
        .filter(user_email=user_email)
        .exclude(role=DocumentPermission.ROLE_OWNER)
        .values_list("document_id", flat=True)
    )
    docs = Document.objects.filter(pk__in=perm_ids)
    result = []
    for doc in docs:
        perm = DocumentPermission.objects.filter(document_id=doc.pk, user_email=user_email).first()
        doc._shared_role = perm.role if perm else None
        doc._shared_granted_by = perm.granted_by if perm else None
        result.append(doc)
    return SharedWithMeSerializer(result, many=True).data
