from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="Realtime Collaboration Helper",
    version="0.1.0",
    description="Small helper service for lightweight preview work.",
)


class PreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to preview")
    max_chars: int = Field(160, ge=20, le=300, description="Maximum preview length")


class PreviewResponse(BaseModel):
    status: Literal["ok"] = "ok"
    word_count: int
    char_count: int
    preview: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "fastapi-helper"}


@app.post("/preview", response_model=PreviewResponse)
async def create_preview(payload: PreviewRequest) -> PreviewResponse:
    cleaned = payload.text.strip()
    words = cleaned.split()
    preview = cleaned

    if len(preview) > payload.max_chars:
        preview = preview[: payload.max_chars].rstrip() + "..."

    return PreviewResponse(
        status="ok",
        word_count=len(words),
        char_count=len(cleaned),
        preview=preview,
    )
