from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from chat.chat_wz import router as chat_router
from login.login import router as login_router

APP_NAME = "RD Auth Service"
_SESSION_COOKIE_NAME = "rd_session"
_DEFAULT_SESSION_SECRET = "rd-dev-secret-change-me"


def _get_allowed_origins() -> list[str]:
    allowed_origins_text = os.getenv(
        "RD_ALLOWED_ORIGINS",
        "http://127.0.0.1:4321,http://127.0.0.1:3000",
    )
    return [item.strip() for item in allowed_origins_text.split(",") if item.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("RD_SESSION_SECRET", _DEFAULT_SESSION_SECRET),
        session_cookie=_SESSION_COOKIE_NAME,
        same_site="lax",
        https_only=False,
        max_age=7 * 24 * 60 * 60,
    )

    app.include_router(login_router)
    app.include_router(chat_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=3000, reload=False)
