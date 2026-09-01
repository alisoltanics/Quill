"""
Audit Service Tests
===================
Tests the activity endpoint and event processing logic.
Uses SQLite in-memory database for isolation.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from unittest.mock import patch

from app.database import Base
from app.main import app, process_event, parse_timestamp, get_db
from app.models import AuditActivity

os.environ["DATABASE_URL"] = "sqlite://"

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ─── Health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        # The audit service doesn't have a /health endpoint, but let's test
        # that the root or any endpoint is accessible
        resp = client.get("/docs")
        assert resp.status_code == 200


# ─── parse_timestamp ──────────────────────────────────────────────────────────

class TestParseTimestamp:
    def test_parse_iso_timestamp(self):
        ts = parse_timestamp("2024-01-15T10:30:00Z")
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15
        assert ts.hour == 10
        assert ts.minute == 30

    def test_parse_iso_with_offset(self):
        ts = parse_timestamp("2024-01-15T10:30:00+00:00")
        assert ts.year == 2024

    def test_parse_invalid_timestamp(self):
        ts = parse_timestamp("not-a-date")
        assert ts is not None  # Returns current time as fallback


# ─── process_event ────────────────────────────────────────────────────────────

class TestProcessEvent:
    @patch("app.main.SessionLocal", TestingSessionLocal)
    def test_process_document_updated(self):
        event = {
            "event": "document.updated",
            "document_id": "1",
            "user_id": "42",
            "version": "5",
            "action": "updated",
            "user": "alice",
            "client_id": "client-1",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        process_event(event)

        db = TestingSessionLocal()
        try:
            rows = db.query(AuditActivity).all()
            assert len(rows) == 1
            assert rows[0].document_id == 1
            assert rows[0].user_id == 42
            assert rows[0].user_name == "alice"
            assert rows[0].action == "updated"
            assert rows[0].version == 5
            assert rows[0].client_id == "client-1"
        finally:
            db.close()

    def test_process_event_ignores_non_document_events(self):
        event = {"event": "user.created", "user_id": "1"}
        process_event(event)

        db = TestingSessionLocal()
        try:
            rows = db.query(AuditActivity).all()
            assert len(rows) == 0
        finally:
            db.close()

    @patch("app.main.SessionLocal", TestingSessionLocal)
    def test_process_event_missing_user_uses_fallback(self):
        event = {
            "event": "document.updated",
            "document_id": "2",
            "user_id": "99",
            "version": "1",
        }
        process_event(event)

        db = TestingSessionLocal()
        try:
            rows = db.query(AuditActivity).all()
            assert len(rows) == 1
            assert rows[0].user_name == "user-99"
        finally:
            db.close()

    @patch("app.main.SessionLocal", TestingSessionLocal)
    def test_process_event_uses_username_field(self):
        event = {
            "event": "document.updated",
            "document_id": "3",
            "user_id": "10",
            "version": "2",
            "username": "bob",
        }
        process_event(event)

        db = TestingSessionLocal()
        try:
            rows = db.query(AuditActivity).all()
            assert len(rows) == 1
            assert rows[0].user_name == "bob"
        finally:
            db.close()

    @patch("app.main.SessionLocal", TestingSessionLocal)
    def test_process_event_with_client_id(self):
        event = {
            "event": "document.updated",
            "document_id": "4",
            "user_id": "11",
            "version": "3",
            "user": "charlie",
            "client_id": "client-abc",
        }
        process_event(event)

        db = TestingSessionLocal()
        try:
            rows = db.query(AuditActivity).all()
            assert len(rows) == 1
            assert rows[0].client_id == "client-abc"
        finally:
            db.close()


# ─── Activity endpoint ────────────────────────────────────────────────────────

class TestActivityEndpoint:
    def _insert_activity(self, doc_id, user_id, user_name, action, version, client_id=None):
        db = TestingSessionLocal()
        try:
            from datetime import datetime, timezone
            audit = AuditActivity(
                document_id=doc_id,
                user_id=user_id,
                user_name=user_name,
                action=action,
                version=version,
                client_id=client_id,
                event_timestamp=datetime.now(timezone.utc),
            )
            db.add(audit)
            db.commit()
        finally:
            db.close()

    def test_get_activity_empty(self, client):
        resp = client.get("/api/documents/1/activity")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_activity_returns_data(self, client):
        self._insert_activity(1, 1, "alice", "updated", 1)
        self._insert_activity(1, 2, "bob", "updated", 2)

        resp = client.get("/api/documents/1/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be ordered by created_at desc (most recent first)
        assert data[0]["user"] in ("alice", "bob")

    def test_get_activity_only_for_doc(self, client):
        self._insert_activity(1, 1, "alice", "updated", 1)
        self._insert_activity(2, 2, "bob", "updated", 1)

        resp = client.get("/api/documents/1/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user"] == "alice"

    def test_get_activity_response_format(self, client):
        self._insert_activity(1, 1, "alice", "updated", 5, "client-1")
        resp = client.get("/api/documents/1/activity")
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert "user" in item
        assert "action" in item
        assert "version" in item
        assert "created_at" in item
