from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from chat.chat_wz import router as chat_router
from doctor_face.face_doc import router as face_doc_router
from doctor_face.face import router as face_router
from docter_tg.tg import router as tg_router
from login.login import router as login_router

APP_NAME = "RD Auth Service"
_SESSION_COOKIE_NAME = "rd_session"
_DEFAULT_SESSION_SECRET = "rd-dev-secret-change-me"
_BASE_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _BASE_DIR / "config.json"


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def _read_allowed_origins_from_config(config: dict[str, Any]) -> list[str]:
    cors = config.get("cors") if isinstance(config.get("cors"), dict) else {}
    configured = cors.get("allowedOrigins") if isinstance(cors.get("allowedOrigins"), list) else []
    origins: list[str] = []
    for item in configured:
        if not isinstance(item, str):
            continue
        normalized = _normalize_origin(item)
        if normalized:
            origins.append(normalized)
    return origins


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _to_int(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return default


def _get_allowed_origins() -> list[str]:
    config = _load_config()
    configured_origins = _read_allowed_origins_from_config(config)

    allowed_origins_text = os.getenv(
        "RD_ALLOWED_ORIGINS",
        ",".join(configured_origins)
        if configured_origins
        else "http://127.0.0.1:4321,http://127.0.0.1:3000,https://tg.wanshushan.top",
    )
    origins: list[str] = []
    for item in allowed_origins_text.split(","):
        normalized = _normalize_origin(item)
        if normalized:
            origins.append(normalized)
    return origins


def create_app() -> FastAPI:
    config = _load_config()
    app_name = str(config.get("appName") or APP_NAME).strip() or APP_NAME
    cors = config.get("cors") if isinstance(config.get("cors"), dict) else {}
    session = config.get("session") if isinstance(config.get("session"), dict) else {}

    app = FastAPI(title=app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_allowed_origins(),
        allow_credentials=_to_bool(cors.get("allowCredentials"), default=True),
        allow_methods=cors.get("allowMethods") if isinstance(cors.get("allowMethods"), list) else ["*"],
        allow_headers=cors.get("allowHeaders") if isinstance(cors.get("allowHeaders"), list) else ["*"],
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv(
            "RD_SESSION_SECRET",
            str(session.get("secret") or _DEFAULT_SESSION_SECRET),
        ),
        session_cookie=str(session.get("cookieName") or _SESSION_COOKIE_NAME),
        same_site=str(session.get("sameSite") or "lax"),
        https_only=_to_bool(session.get("httpsOnly"), default=False),
        max_age=_to_int(session.get("maxAgeSeconds"), default=7 * 24 * 60 * 60),
    )

    app.include_router(login_router)
    app.include_router(chat_router)
    app.include_router(face_router)
    app.include_router(face_doc_router)
    app.include_router(tg_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    runtime_config = _load_config()
    server = runtime_config.get("server") if isinstance(runtime_config.get("server"), dict) else {}
    host = str(server.get("host") or "127.0.0.1")
    port = _to_int(server.get("port"), default=3000)

    uvicorn.run("main:app", host=host, port=port, reload=False)
