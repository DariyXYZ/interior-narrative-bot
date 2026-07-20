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
from app.domain import quiz_engine
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


class ProjectCreate(BaseModel):
    code_name: str = Field(min_length=1, max_length=120)
    object_type: str | None = Field(default=None, max_length=64)
    area_m2: float | None = Field(default=None, ge=0, le=1_000_000)
    project_started_on: str | None = Field(default=None, max_length=32)
    concept_due_on: str | None = Field(default=None, max_length=32)
    presentation_on: str | None = Field(default=None, max_length=32)
    implementation_on: str | None = Field(default=None, max_length=32)


class AnswerSubmit(BaseModel):
    option_id: str = Field(min_length=1, max_length=32)


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


@app.get("/api/v1/tests/{test_key}")
async def get_test_content(test_key: str, _user: Annotated[dict, Depends(current_user)]) -> dict:
    try:
        content = quiz_engine.load_content(test_key)
    except quiz_engine.ContentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "test_key": content["test_key"],
        "version": content["version"],
        "title": content["title"],
        "duration_hint": content["duration_hint"],
        "questions": quiz_engine.public_questions(content),
    }


@app.post("/api/v1/projects", status_code=201)
async def create_project(payload: ProjectCreate, user: Annotated[dict, Depends(current_user)]) -> dict:
    return await repository.create_project(
        user["id"],
        payload.code_name,
        payload.object_type,
        payload.area_m2,
        payload.project_started_on,
        payload.concept_due_on,
        payload.presentation_on,
        payload.implementation_on,
    )


@app.post("/api/v1/sessions", status_code=201)
async def start_session(payload: SessionCreate, user: Annotated[dict, Depends(current_user)]) -> dict:
    if payload.test_key == "project-narrative" and not payload.project_id:
        raise HTTPException(status_code=422, detail="Для теста project-narrative нужен project_id")
    try:
        session = await repository.create_session(user["id"], payload.test_key, payload.project_id)
    except aiosqlite.IntegrityError as exc:
        raise HTTPException(status_code=422, detail="Неизвестный project_id") from exc
    await repository.log_event("session_started", user["id"], session["id"], {"test_key": payload.test_key})
    return session


async def _owned_session(session_id: str, user: dict) -> dict:
    session = await repository.get_session(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return session


@app.get("/api/v1/sessions/{session_id}")
async def get_session(session_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    session = await _owned_session(session_id, user)
    answers = await repository.list_session_answers(session_id)
    return {**session, "answers": answers}


@app.put("/api/v1/sessions/{session_id}/answers/{question_id}")
async def submit_answer(
    session_id: str, question_id: str, payload: AnswerSubmit, user: Annotated[dict, Depends(current_user)]
) -> dict:
    session = await _owned_session(session_id, user)
    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="Сессия уже завершена")
    try:
        content = quiz_engine.load_content(session["test_key"])
    except quiz_engine.ContentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    question = next((q for q in content["questions"] if q["id"] == question_id), None)
    if question is None or not any(o["id"] == payload.option_id for o in question["options"]):
        raise HTTPException(status_code=422, detail="Неизвестный вопрос или вариант ответа")
    await repository.upsert_answer(session_id, question_id, payload.option_id)
    return {"status": "saved"}


@app.post("/api/v1/sessions/{session_id}/complete")
async def complete_session(session_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    session = await _owned_session(session_id, user)
    if session["status"] != "in_progress":
        existing = await repository.get_result(session_id, user["id"])
        if existing is not None:
            return existing
        raise HTTPException(status_code=409, detail="Сессия уже завершена без результата")
    try:
        content = quiz_engine.load_content(session["test_key"])
    except quiz_engine.ContentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    answers = await repository.list_session_answers(session_id)
    result = quiz_engine.compose_result(session["test_key"], content, answers)
    await repository.complete_session(session_id, result)
    await repository.log_event(
        "session_completed", user["id"], session_id,
        {"test_key": session["test_key"], "primary_narrative_key": result["primary_narrative_key"]},
    )
    full = await repository.get_result(session_id, user["id"])
    return full


@app.get("/api/v1/sessions/{session_id}/result")
async def get_session_result(session_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    result = await repository.get_result(session_id, user["id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Результат не найден")
    content = quiz_engine.load_content(result["test_key"])
    result["primary_detail"] = quiz_engine.narrative_detail(content, result["primary_narrative_key"])
    for alt in result["alternatives"]:
        alt["detail"] = quiz_engine.narrative_detail(content, alt["key"])
    result["full_ranking"] = quiz_engine.full_ranking(content, result["scoring_trace"]["ranked"])
    return result


@app.get("/api/v1/results")
async def results(user: Annotated[dict, Depends(current_user)]) -> list[dict]:
    rows = await repository.list_user_results(user["id"])
    for row in rows:
        content = quiz_engine.load_content(row["test_key"])
        narrative = content["narratives"].get(row["primary_narrative_key"], {})
        row["primary_narrative_name"] = narrative.get("name", row["primary_narrative_key"])
        row["primary_narrative_color"] = narrative.get("color")
    return rows


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
