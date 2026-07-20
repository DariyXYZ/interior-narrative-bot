from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import aiosqlite
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.telegram_auth import TelegramAuthError, TelegramIdentity, validate_init_data
from app.core.config import BASE_DIR, get_settings
from app.storage import repository

WEBAPP_DIR = BASE_DIR / "webapp"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await repository.init_db()
    yield


app = FastAPI(
    title="IND Interior Narrative API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data", "ngrok-skip-browser-warning"],
)
app.mount("/assets", StaticFiles(directory=WEBAPP_DIR / "assets"), name="assets")


class SessionCreate(BaseModel):
    test_key: Literal["designer-profile", "project-narrative"]
    project_id: str | None = Field(default=None, max_length=64)


async def telegram_identity(
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> TelegramIdentity:
    settings = get_settings()
    try:
        return validate_init_data(
            x_telegram_init_data or "",
            settings.require_bot_token(),
            settings.init_data_max_age_seconds,
        )
    except (TelegramAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def current_user(identity: Annotated[TelegramIdentity, Depends(telegram_identity)]) -> dict:
    return await repository.upsert_telegram_user(identity.user)


@app.get("/api/v1/health")
async def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/v1/me")
async def me(user: Annotated[dict, Depends(current_user)]) -> dict:
    return {
        "telegram_user_id": user["telegram_user_id"],
        "username": user["username"],
        "first_name": user["first_name"],
    }


@app.post("/api/v1/sessions", status_code=201)
async def start_session(payload: SessionCreate, user: Annotated[dict, Depends(current_user)]) -> dict:
    try:
        session = await repository.create_session(user["id"], payload.test_key, payload.project_id)
    except aiosqlite.IntegrityError as exc:
        raise HTTPException(status_code=422, detail="Неизвестный project_id") from exc
    await repository.log_event("session_started", user["id"], session["id"], {"test_key": payload.test_key})
    return session


@app.get("/api/v1/results")
async def results(user: Annotated[dict, Depends(current_user)]) -> list[dict]:
    return await repository.list_user_results(user["id"])


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEBAPP_DIR / "index.html")


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Не найдено")
    candidate = (WEBAPP_DIR / path).resolve()
    if candidate.is_file() and WEBAPP_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(WEBAPP_DIR / "index.html")
