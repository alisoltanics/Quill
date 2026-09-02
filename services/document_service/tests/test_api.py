import json
import time
from unittest.mock import patch

import jwt
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import Document, DocumentPermission, DocumentVersion, Folder

JWT_SECRET = "test-secret"
MODULE = "api.views"


def _token(user_id: int, email: str = "test@example.com") -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _auth(client: APIClient, user_id: int, email: str = "test@example.com"):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token(user_id, email)}")


class HealthTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")


# ─── Folders ─────────────────────────────────────────────────────────────────

class FolderListTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_empty(self):
        resp = self.client.get("/folders")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["folders"], [])

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_returns_own_folders(self):
        Folder.objects.create(user_id=self.uid, name="My Folder")
        Folder.objects.create(user_id=999, name="Other Folder")
        resp = self.client.get("/folders")
        self.assertEqual(len(resp.json()["folders"]), 1)
        self.assertEqual(resp.json()["folders"][0]["name"], "My Folder")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_folder_default_name(self):
        resp = self.client.post("/folders", {}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "New Folder")
        self.assertEqual(Folder.objects.count(), 1)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_folder_custom_name(self):
        resp = self.client.post("/folders", {"name": "Designs"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "Designs")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_folder_with_idempotency_key_replays(self):
        # First request creates; replay with the same key returns the same folder.
        first = self.client.post(
            "/folders", {"name": "Designs"}, format="json",
            HTTP_IDEMPOTENCY_KEY="op-123",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["name"], "Designs")

        second = self.client.post(
            "/folders", {"name": "Designs"}, format="json",
            HTTP_IDEMPOTENCY_KEY="op-123",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(Folder.objects.count(), 1)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_folder_different_keys_create_separate_folders(self):
        self.client.post(
            "/folders", {"name": "A"}, format="json", HTTP_IDEMPOTENCY_KEY="op-1"
        )
        self.client.post(
            "/folders", {"name": "B"}, format="json", HTTP_IDEMPOTENCY_KEY="op-2"
        )
        self.assertEqual(Folder.objects.count(), 2)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_idempotency_key_is_scoped_to_user(self):
        self.client.post(
            "/folders", {"name": "Mine"}, format="json", HTTP_IDEMPOTENCY_KEY="op-123"
        )
        # A different user reusing the same key gets their own folder.
        _auth(self.client, 200)
        resp = self.client.post(
            "/folders", {"name": "Yours"}, format="json", HTTP_IDEMPOTENCY_KEY="op-123"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "Yours")
        self.assertEqual(Folder.objects.count(), 2)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_folder_without_key_is_not_idempotent(self):
        self.client.post("/folders", {"name": "Designs"}, format="json")
        self.client.post("/folders", {"name": "Designs"}, format="json")
        self.assertEqual(Folder.objects.count(), 2)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_folder_rejects_oversized_idempotency_key(self):
        resp = self.client.post(
            "/folders", {"name": "Designs"}, format="json",
            HTTP_IDEMPOTENCY_KEY="k" * 256,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Folder.objects.count(), 0)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_unauthenticated_list(self):
        client = APIClient()
        resp = client.get("/folders")
        self.assertEqual(resp.status_code, 403)


class FolderDetailTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)
        self.folder = Folder.objects.create(user_id=self.uid, name="Test Folder")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_folder_name(self):
        resp = self.client.patch(f"/folders/{self.folder.pk}", {"name": "Renamed"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Renamed")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_folder_not_found(self):
        resp = self.client.patch("/folders/9999", {"name": "X"}, format="json")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_other_users_folder(self):
        _auth(self.client, 200)
        resp = self.client.patch(f"/folders/{self.folder.pk}", {"name": "Hacked"}, format="json")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_folder(self):
        resp = self.client.delete(f"/folders/{self.folder.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], self.folder.pk)
        self.assertFalse(Folder.objects.filter(pk=self.folder.pk).exists())

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_folder_not_found(self):
        resp = self.client.delete("/folders/9999")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_unlinks_documents(self):
        doc = Document.objects.create(user_id=self.uid, folder=self.folder)
        self.client.delete(f"/folders/{self.folder.pk}")
        doc.refresh_from_db()
        self.assertIsNone(doc.folder)


# ─── Documents ───────────────────────────────────────────────────────────────

class DocumentListTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_empty(self):
        resp = self.client.get("/documents")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["folders"], [])
        self.assertEqual(data["documents"], [])

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_root_documents(self):
        Document.objects.create(user_id=self.uid, title="Doc1")
        Document.objects.create(user_id=999, title="Other")
        resp = self.client.get("/documents")
        docs = resp.json()["documents"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["title"], "Doc1")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_documents_in_folders(self):
        folder = Folder.objects.create(user_id=self.uid, name="F1")
        Document.objects.create(user_id=self.uid, folder=folder, title="InFolder")
        resp = self.client.get("/documents")
        folders = resp.json()["folders"]
        self.assertEqual(len(folders), 1)
        self.assertEqual(len(folders[0]["documents"]), 1)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_document(self):
        resp = self.client.post("/documents", {"title": "New Doc"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["title"], "New Doc")
        self.assertEqual(Document.objects.count(), 1)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_document_in_folder(self):
        folder = Folder.objects.create(user_id=self.uid, name="F1")
        resp = self.client.post("/documents", {"title": "In F1", "folder_id": folder.pk}, format="json")
        self.assertEqual(resp.status_code, 201)
        doc = Document.objects.get(pk=resp.json()["id"])
        self.assertEqual(doc.folder_id, folder.pk)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_document_invalid_folder(self):
        resp = self.client.post("/documents", {"folder_id": 9999}, format="json")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_create_document_default_title(self):
        resp = self.client.post("/documents", {}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["title"], "Untitled")


class DocumentDetailTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)
        self.doc = Document.objects.create(user_id=self.uid, title="My Doc", content="hello")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_get_document(self):
        resp = self.client.get(f"/documents/{self.doc.pk}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "My Doc")
        self.assertEqual(data["content"], "hello")
        self.assertIn("versions", data)
        self.assertIsInstance(data["versions"], list)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_get_document_not_found(self):
        resp = self.client.get("/documents/9999")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_get_document_no_access(self):
        _auth(self.client, 999)
        resp = self.client.get(f"/documents/{self.doc.pk}")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_get_document_viewer_access(self):
        _auth(self.client, 200, "viewer@test.com")
        DocumentPermission.objects.create(
            document=self.doc, user_email="viewer@test.com",
            role="viewer", granted_by="test@example.com",
        )
        resp = self.client.get(f"/documents/{self.doc.pk}")
        self.assertEqual(resp.status_code, 200)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_title(self):
        resp = self.client.patch(f"/documents/{self.doc.pk}", {"title": "Updated"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Updated")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_content_full_replace(self):
        resp = self.client.patch(f"/documents/{self.doc.pk}", {"content": "new"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.content, "new")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_content_append(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}",
            {"content": " world", "full": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.content, "hello\n world")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_creates_version(self):
        self.client.patch(f"/documents/{self.doc.pk}", {"content": "v2"}, format="json")
        self.assertEqual(DocumentVersion.objects.filter(document=self.doc).count(), 1)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_no_content_no_version(self):
        self.client.patch(f"/documents/{self.doc.pk}", {"title": "Just Title"}, format="json")
        self.assertEqual(DocumentVersion.objects.filter(document=self.doc).count(), 0)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_yjs_state(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}",
            {"yjs_state": "abc123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.yjs_state, "abc123")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_yjsState_alias(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}",
            {"yjsState": "xyz"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.yjs_state, "xyz")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_editor_access(self):
        _auth(self.client, 200, "editor@test.com")
        DocumentPermission.objects.create(
            document=self.doc, user_email="editor@test.com",
            role="editor", granted_by="test@example.com",
        )
        resp = self.client.patch(f"/documents/{self.doc.pk}", {"title": "Edit"}, format="json")
        self.assertEqual(resp.status_code, 200)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_viewer_forbidden(self):
        _auth(self.client, 200, "viewer@test.com")
        DocumentPermission.objects.create(
            document=self.doc, user_email="viewer@test.com",
            role="viewer", granted_by="test@example.com",
        )
        resp = self.client.patch(f"/documents/{self.doc.pk}", {"title": "Nope"}, format="json")
        self.assertEqual(resp.status_code, 403)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_move_folder_owner_only(self):
        _auth(self.client, 200, "editor@test.com")
        DocumentPermission.objects.create(
            document=self.doc, user_email="editor@test.com",
            role="editor", granted_by="test@example.com",
        )
        resp = self.client.patch(f"/documents/{self.doc.pk}", {"folder_id": None}, format="json")
        self.assertEqual(resp.status_code, 403)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_move_folder_invalid(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}",
            {"folder_id": 9999},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_document(self):
        resp = self.client.delete(f"/documents/{self.doc.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], self.doc.pk)
        self.assertFalse(Document.objects.filter(pk=self.doc.pk).exists())

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_document_not_found(self):
        resp = self.client.delete("/documents/9999")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_other_users_document(self):
        _auth(self.client, 999)
        resp = self.client.delete(f"/documents/{self.doc.pk}")
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_empty_body(self):
        resp = self.client.patch(f"/documents/{self.doc.pk}", {}, format="json")
        self.assertEqual(resp.status_code, 200)

    @patch("api.commands._publish_redis")
    @patch("api.commands._publish_kafka")
    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_content_publishes(self, mock_kafka, mock_redis):
        self.client.patch(
            f"/documents/{self.doc.pk}",
            {"yjs_state": "sync"},
            format="json",
        )
        mock_redis.assert_called_once()
        mock_kafka.assert_called_once()


# ─── Sharing ─────────────────────────────────────────────────────────────────

class DocumentShareTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)
        self.doc = Document.objects.create(user_id=self.uid, title="Shared Doc")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_document(self):
        resp = self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"email": "bob@test.com", "role": "editor"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["user_email"], "bob@test.com")
        self.assertEqual(resp.json()["role"], "editor")
        self.assertEqual(DocumentPermission.objects.count(), 1)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_default_role(self):
        resp = self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"email": "bob@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["role"], "viewer")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_update_existing(self):
        self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"email": "bob@test.com", "role": "viewer"},
            format="json",
        )
        resp = self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"email": "bob@test.com", "role": "editor"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["role"], "editor")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_self_forbidden(self):
        resp = self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"email": "test@example.com", "role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_missing_email(self):
        resp = self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_invalid_role(self):
        resp = self.client.post(
            f"/documents/{self.doc.pk}/share",
            {"email": "bob@test.com", "role": "admin"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_share_not_found(self):
        resp = self.client.post(
            "/documents/9999/share",
            {"email": "bob@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_permissions(self):
        DocumentPermission.objects.create(
            document=self.doc, user_email="bob@test.com",
            role="editor", granted_by="test@example.com",
        )
        resp = self.client.get(f"/documents/{self.doc.pk}/permissions")
        self.assertEqual(resp.status_code, 200)
        perms = resp.json()["permissions"]
        self.assertEqual(len(perms), 1)
        self.assertEqual(perms[0]["user_email"], "bob@test.com")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_permissions_not_found(self):
        resp = self.client.get("/documents/9999/permissions")
        self.assertEqual(resp.status_code, 404)


class DocumentPermissionDetailTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)
        self.doc = Document.objects.create(user_id=self.uid, title="Doc")
        self.perm = DocumentPermission.objects.create(
            document=self.doc, user_email="bob@test.com",
            role="editor", granted_by="test@example.com",
        )

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_permission_role(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}/permissions/bob@test.com",
            {"role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.perm.refresh_from_db()
        self.assertEqual(self.perm.role, "viewer")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_permission_invalid_role(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}/permissions/bob@test.com",
            {"role": "admin"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_permission_not_found(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}/permissions/nobody@test.com",
            {"role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_patch_permission_forbidden_non_owner(self):
        _auth(self.client, 200, "editor@test.com")
        DocumentPermission.objects.create(
            document=self.doc, user_email="editor@test.com",
            role="editor", granted_by="test@example.com",
        )
        resp = self.client.patch(
            f"/documents/{self.doc.pk}/permissions/bob@test.com",
            {"role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_permission(self):
        resp = self.client.delete(
            f"/documents/{self.doc.pk}/permissions/bob@test.com",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(DocumentPermission.objects.filter(pk=self.perm.pk).exists())

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_permission_not_found(self):
        resp = self.client.delete(
            f"/documents/{self.doc.pk}/permissions/nobody@test.com",
        )
        self.assertEqual(resp.status_code, 404)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_delete_permission_forbidden_non_owner(self):
        _auth(self.client, 200, "editor@test.com")
        DocumentPermission.objects.create(
            document=self.doc, user_email="editor@test.com",
            role="editor", granted_by="test@example.com",
        )
        resp = self.client.delete(
            f"/documents/{self.doc.pk}/permissions/bob@test.com",
        )
        self.assertEqual(resp.status_code, 403)


class LastOwnerProtectionTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        _auth(self.client, self.uid)
        self.doc = Document.objects.create(user_id=self.uid, title="Doc")
        self.owner_perm = DocumentPermission.objects.create(
            document=self.doc, user_email="test@example.com",
            role="owner", granted_by="test@example.com",
        )

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_cannot_demote_last_owner(self):
        resp = self.client.patch(
            f"/documents/{self.doc.pk}/permissions/test@example.com",
            {"role": "editor"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_cannot_delete_last_owner(self):
        resp = self.client.delete(
            f"/documents/{self.doc.pk}/permissions/test@example.com",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_can_demote_owner_with_multiple_owners(self):
        DocumentPermission.objects.create(
            document=self.doc, user_email="other@test.com",
            role="owner", granted_by="test@example.com",
        )
        resp = self.client.patch(
            f"/documents/{self.doc.pk}/permissions/test@example.com",
            {"role": "editor"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_can_delete_owner_with_multiple_owners(self):
        DocumentPermission.objects.create(
            document=self.doc, user_email="other@test.com",
            role="owner", granted_by="test@example.com",
        )
        resp = self.client.delete(
            f"/documents/{self.doc.pk}/permissions/test@example.com",
        )
        self.assertEqual(resp.status_code, 200)


# ─── Shared With Me ──────────────────────────────────────────────────────────

class SharedWithMeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.uid = 100
        self.email = "me@test.com"
        _auth(self.client, self.uid, self.email)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_shared_documents(self):
        other_uid = 200
        doc = Document.objects.create(user_id=other_uid, title="Shared")
        DocumentPermission.objects.create(
            document=doc, user_email=self.email,
            role="editor", granted_by="other@test.com",
        )
        resp = self.client.get("/shared-with-me")
        self.assertEqual(resp.status_code, 200)
        docs = resp.json()["documents"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["title"], "Shared")
        self.assertEqual(docs[0]["role"], "editor")
        self.assertEqual(docs[0]["granted_by"], "other@test.com")

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_excludes_owned_documents(self):
        doc = Document.objects.create(user_id=self.uid, title="Mine")
        DocumentPermission.objects.create(
            document=doc, user_email=self.email,
            role="owner", granted_by="self@test.com",
        )
        resp = self.client.get("/shared-with-me")
        self.assertEqual(len(resp.json()["documents"]), 0)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_list_empty(self):
        resp = self.client.get("/shared-with-me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["documents"], [])


# ─── Auth edge cases ─────────────────────────────────────────────────────────

class AuthEdgeCaseTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_no_auth_header(self):
        resp = self.client.get("/folders")
        self.assertEqual(resp.status_code, 403)

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_invalid_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        resp = self.client.get("/folders")
        self.assertIn(resp.status_code, [401, 403])

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_non_access_token(self):
        payload = {
            "sub": "100",
            "email": "test@test.com",
            "type": "refresh",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/folders")
        self.assertIn(resp.status_code, [401, 403])

    @patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)
    def test_expired_token(self):
        payload = {
            "sub": "100",
            "email": "test@test.com",
            "type": "access",
            "exp": int(time.time()) - 3600,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/folders")
        self.assertIn(resp.status_code, [401, 403])
