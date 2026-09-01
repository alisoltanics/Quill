"""
Export Service Tests
====================
Tests conversion helpers, health endpoint, and export routes.
Uses httpx.AsyncClient with ASGI transport for async testing.
"""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, _to_markdown, _to_txt, _convert

TEST_SECRET = "test-export-secret"
MODULE = "app.main"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ─── Conversion helpers ───────────────────────────────────────────────────────

class TestConversionHelpers:
    def test_to_markdown_paragraph(self):
        html = "<p>Hello world</p>"
        md = _to_markdown(html)
        assert "Hello world" in md

    def test_to_markdown_heading(self):
        html = "<h1>Title</h1>"
        md = _to_markdown(html)
        assert "Title" in md

    def test_to_markdown_bold(self):
        html = "<p><strong>bold text</strong></p>"
        md = _to_markdown(html)
        assert "bold text" in md

    def test_to_markdown_list(self):
        html = "<ul><li>item1</li><li>item2</li></ul>"
        md = _to_markdown(html)
        assert "item1" in md
        assert "item2" in md

    def test_to_markdown_strips_images(self):
        html = '<p>Text <img src="test.png" alt="img"> end</p>'
        md = _to_markdown(html)
        assert "Text" in md
        assert "end" in md

    def test_to_txt_strips_tags(self):
        html = "<p>Hello <strong>world</strong></p>"
        txt = _to_txt(html)
        assert "Hello world" in txt
        assert "<" not in txt

    def test_to_txt_collapses_whitespace(self):
        html = "<p>Hello   world</p>"
        txt = _to_txt(html)
        assert "  " not in txt

    def test_to_txt_empty_string(self):
        txt = _to_txt("")
        assert txt == ""

    def test_convert_html(self):
        body, media_type = _convert("<p>test</p>", "html")
        assert "<p>test</p>" in body
        assert "text/html" in media_type

    def test_convert_markdown(self):
        body, media_type = _convert("<p>test</p>", "markdown")
        assert "test" in body
        assert "text/markdown" in media_type

    def test_convert_txt(self):
        body, media_type = _convert("<p>test</p>", "txt")
        assert "test" in body
        assert "text/plain" in media_type


# ─── Health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "export-service"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_export_requires_auth(self, client):
        resp = client.get("/export/1?format=markdown")
        assert resp.status_code == 403

    @patch(f"{MODULE}._JWT_SECRET", TEST_SECRET)
    def test_export_invalid_token(self, client):
        resp = client.get("/export/1?format=markdown", headers={
            "Authorization": "Bearer invalid-token",
        })
        assert resp.status_code == 401

    @patch(f"{MODULE}._JWT_SECRET", TEST_SECRET)
    def test_export_refresh_token_rejected(self, client):
        from jose import jwt
        token = jwt.encode(
            {"sub": "1", "type": "refresh"},
            TEST_SECRET,
            algorithm="HS256",
        )
        resp = client.get("/export/1?format=markdown", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401

    def test_post_export_requires_auth(self, client):
        resp = client.post("/export?format=markdown", json={"content": "<p>test</p>"})
        assert resp.status_code == 403


# ─── POST /export ─────────────────────────────────────────────────────────────

class TestPostExport:
    def _get_token(self):
        from jose import jwt
        return jwt.encode(
            {"sub": "1", "email": "test@test.com", "type": "access"},
            TEST_SECRET,
            algorithm="HS256",
        )

    @patch(f"{MODULE}._JWT_SECRET", TEST_SECRET)
    def test_post_export_markdown(self, client):
        token = self._get_token()
        resp = client.post(
            "/export?format=markdown",
            json={"content": "<p>Hello world</p>"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "Hello world" in resp.text

    @patch(f"{MODULE}._JWT_SECRET", TEST_SECRET)
    def test_post_export_txt(self, client):
        token = self._get_token()
        resp = client.post(
            "/export?format=txt",
            json={"content": "<p>Hello <strong>world</strong></p>"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "Hello world" in resp.text

    @patch(f"{MODULE}._JWT_SECRET", TEST_SECRET)
    def test_post_export_html_passthrough(self, client):
        token = self._get_token()
        resp = client.post(
            "/export?format=html",
            json={"content": "<p>Hello world</p>"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "<p>Hello world</p>" in resp.text

    @patch(f"{MODULE}._JWT_SECRET", TEST_SECRET)
    def test_post_export_default_format(self, client):
        token = self._get_token()
        resp = client.post(
            "/export",
            json={"content": "<p>Hello</p>"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "Hello" in resp.text


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_html_conversion(self):
        body, mt = _convert("", "html")
        assert body == ""

        body, mt = _convert("", "markdown")
        assert body == ""

        body, mt = _convert("", "txt")
        assert body == ""
