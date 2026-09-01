"""
Auth Service Tests
==================
Tests registration, login, token refresh, and /me endpoint.
Uses SQLite aiosqlite in-memory database for isolation.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.auth import create_access_token, create_refresh_token

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    import asyncio

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop().run_until_complete(_create())
    yield

    async def _drop():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.get_event_loop().run_until_complete(_drop())


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ─── Health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "auth-service"


# ─── Registration ─────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client):
        client.post("/auth/register", json={
            "email": "dup@example.com",
            "password": "password123",
        })
        resp = client.post("/auth/register", json={
            "email": "dup@example.com",
            "password": "password456",
        })
        assert resp.status_code == 409

    def test_register_short_password(self, client):
        resp = client.post("/auth/register", json={
            "email": "short@example.com",
            "password": "123",
        })
        assert resp.status_code == 422

    def test_register_invalid_email(self, client):
        resp = client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "password123",
        })
        assert resp.status_code == 422

    def test_register_missing_fields(self, client):
        resp = client.post("/auth/register", json={})
        assert resp.status_code == 422


# ─── Login ────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success(self, client):
        client.post("/auth/register", json={
            "email": "login@example.com",
            "password": "password123",
        })
        resp = client.post("/auth/login", json={
            "email": "login@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_wrong_password(self, client):
        client.post("/auth/register", json={
            "email": "wrong@example.com",
            "password": "password123",
        })
        resp = client.post("/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_login_returns_valid_tokens(self, client):
        client.post("/auth/register", json={
            "email": "token@example.com",
            "password": "password123",
        })
        resp = client.post("/auth/login", json={
            "email": "token@example.com",
            "password": "password123",
        })
        data = resp.json()
        from app.auth import decode_access_token, decode_refresh_token
        access_claims = decode_access_token(data["access_token"])
        refresh_claims = decode_refresh_token(data["refresh_token"])
        assert access_claims["type"] == "access"
        assert refresh_claims["type"] == "refresh"


# ─── Refresh ──────────────────────────────────────────────────────────────────

class TestRefresh:
    def test_refresh_success(self, client):
        client.post("/auth/register", json={
            "email": "refresh@example.com",
            "password": "password123",
        })
        login_resp = client.post("/auth/login", json={
            "email": "refresh@example.com",
            "password": "password123",
        })
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_invalid_token(self, client):
        resp = client.post("/auth/refresh", json={
            "refresh_token": "invalid-token",
        })
        assert resp.status_code == 401

    def test_refresh_access_token_rejected(self, client):
        client.post("/auth/register", json={
            "email": "access@example.com",
            "password": "password123",
        })
        login_resp = client.post("/auth/login", json={
            "email": "access@example.com",
            "password": "password123",
        })
        access_token = login_resp.json()["access_token"]

        resp = client.post("/auth/refresh", json={
            "refresh_token": access_token,
        })
        assert resp.status_code == 401


# ─── /auth/me ─────────────────────────────────────────────────────────────────

class TestMe:
    def test_me_authenticated(self, client):
        client.post("/auth/register", json={
            "email": "me@example.com",
            "password": "password123",
        })
        login_resp = client.post("/auth/login", json={
            "email": "me@example.com",
            "password": "password123",
        })
        access_token = login_resp.json()["access_token"]

        resp = client.get("/auth/me", headers={
            "Authorization": f"Bearer {access_token}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "me@example.com"
        assert "id" in data

    def test_me_no_auth(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 403

    def test_me_invalid_token(self, client):
        resp = client.get("/auth/me", headers={
            "Authorization": "Bearer invalid-token",
        })
        assert resp.status_code == 401

    def test_me_refresh_token_rejected(self, client):
        client.post("/auth/register", json={
            "email": "refresh_me@example.com",
            "password": "password123",
        })
        login_resp = client.post("/auth/login", json={
            "email": "refresh_me@example.com",
            "password": "password123",
        })
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.get("/auth/me", headers={
            "Authorization": f"Bearer {refresh_token}",
        })
        assert resp.status_code == 401


# ─── Token type validation ────────────────────────────────────────────────────

class TestTokenTypes:
    def test_access_token_contains_email(self):
        from app.auth import decode_access_token
        token = create_access_token(42, "user@test.com")
        claims = decode_access_token(token)
        assert claims["email"] == "user@test.com"
        assert claims["sub"] == "42"

    def test_refresh_token_no_email(self):
        from app.auth import decode_refresh_token
        token = create_refresh_token(42)
        claims = decode_refresh_token(token)
        assert claims["sub"] == "42"
        assert "email" not in claims
