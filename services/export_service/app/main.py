"""
Export Service
==============
Fetches a document from the Document Service and converts it to the
requested format: html | markdown | txt.

Endpoints
---------
GET  /health
GET  /export/{doc_id}?format=html|markdown|txt
POST /export?format=html|markdown|txt   (body: {"content": "<html>..."})
"""

import os
import re
from typing import Literal

import httpx
import html2text
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

DOCUMENT_SERVICE_URL = os.environ.get(
    "DOCUMENT_SERVICE_URL", "http://document-service:8000"
)
_JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
_ALGORITHM = "HS256"

ExportFormat = Literal["html", "markdown", "txt"]

app = FastAPI(
    title="Export Service",
    version="1.0.0",
    description="Converts collaborative documents to HTML, Markdown, or plain text.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

_bearer = HTTPBearer()


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    try:
        payload = jwt.decode(credentials.credentials, _JWT_SECRET, algorithms=[_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _to_markdown(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0          # no line wrapping
    return converter.handle(html).strip()


def _to_txt(html: str) -> str:
    # strip all tags, collapse whitespace
    no_tags = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r" {2,}", " ", no_tags).strip()


def _convert(html_content: str, fmt: ExportFormat) -> tuple[str, str]:
    """Return (body, media_type)."""
    if fmt == "html":
        return html_content, "text/html; charset=utf-8"
    if fmt == "markdown":
        return _to_markdown(html_content), "text/markdown; charset=utf-8"
    return _to_txt(html_content), "text/plain; charset=utf-8"


async def _fetch_doc(doc_id: int) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{DOCUMENT_SERVICE_URL}/apply/{doc_id}/")
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Document service unreachable: {exc}") from exc
    if resp.status_code == 404:
        raise HTTPException(404, f"Document {doc_id} not found")
    if resp.status_code != 200:
        raise HTTPException(502, f"Document service returned {resp.status_code}")
    return resp.json().get("content", "")


# ─── routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "export-service"}


@app.get(
    "/export/{doc_id}",
    summary="Fetch a document and export it",
    response_class=Response,
)
async def export_by_id(
    doc_id: int,
    format: ExportFormat = Query("markdown", description="Output format"),
    _: dict = Depends(require_auth),
) -> Response:
    html_content = await _fetch_doc(doc_id)
    body, media_type = _convert(html_content, format)
    return Response(content=body, media_type=media_type)


class ExportPayload(BaseModel):
    content: str


@app.post(
    "/export",
    summary="Convert provided HTML content",
    response_class=Response,
)
async def export_content(
    payload: ExportPayload,
    format: ExportFormat = Query("markdown", description="Output format"),
    _: dict = Depends(require_auth),
) -> Response:
    body, media_type = _convert(payload.content, format)
    return Response(content=body, media_type=media_type)

