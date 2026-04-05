from __future__ import annotations

import hashlib
import hmac
import mimetypes
import re
import secrets
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from storage.db import (
    create_user,
    get_user,
    initialize_database,
    list_scores,
    update_user_avatar,
    upsert_user_model_option,
)

try:
    from PIL import Image, UnidentifiedImageError
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("缺少依赖 Pillow，请先安装：pip install pillow") from exc

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
AVATAR_ROOT_DIR = DATA_DIR / "avatar"
LEGACY_AVATAR_DIR = DATA_DIR / "avatars"

_PASSWORD_ITERATIONS = 120_000
_USER_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
_MAX_AVATAR_UPLOAD_BYTES = 5 * 1024 * 1024
_ALLOWED_MODEL_SCOPES = {"chat", "mental", "face"}

initialize_database()


def _normalize_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    _, actual_hash = _hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(actual_hash, expected_hash_hex)


def _valid_username(username: str) -> bool:
    return bool(_USER_NAME_REGEX.match(username))


def _valid_password(password: str) -> bool:
    return 6 <= len(password) <= 72


def _json_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
        },
    )


def _score_points_from_records(records: list[dict[str, Any]]) -> list[dict[str, int]]:
    if not records:
        return []
    normalized: list[tuple[str, int]] = []
    for item in records:
        score = item.get("score")
        time_text = _normalize_text(item.get("time"))
        if not isinstance(score, int):
            continue
        normalized.append((time_text, max(0, min(100, score))))

    if not normalized:
        return []

    normalized.sort(key=lambda value: value[0])
    return [{"x": index + 1, "y": score} for index, (_, score) in enumerate(normalized)]


def _build_chart_points(seed: int, offset: int, amp: int) -> list[dict[str, int]]:
    points: list[dict[str, int]] = []
    for index in range(1, 7):
        y = offset + ((seed + index * 7) % amp)
        points.append({"x": index, "y": y})
    return points


def _build_user_charts(username: str) -> list[dict[str, Any]]:
    seed = sum(ord(char) for char in username)
    face_points = _score_points_from_records(list_scores(username, "face"))
    tg_points = _score_points_from_records(list_scores(username, "tg"))

    return [
        {"id": "chart-1", "points": face_points},
        {"id": "chart-2", "points": tg_points},
        {"id": "chart-3", "points": _build_chart_points(seed + 11, 42, 32)},
        {"id": "chart-4", "points": _build_chart_points(seed + 17, 12, 20)},
    ]


def _get_session_username(request: Request) -> str:
    value = request.session.get("username")
    return _normalize_text(value)


def _get_session_logged_in(request: Request) -> bool:
    value = request.session.get("loggedIn")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    if isinstance(value, (int, float)):
        return int(value) == 1
    return False


def _get_authenticated_username(request: Request) -> tuple[str, dict[str, Any]]:
    username = _get_session_username(request)
    logged_in = _get_session_logged_in(request) or bool(username)
    if not logged_in or not username:
        raise PermissionError("未登录")

    user_obj = get_user(username)
    if not user_obj:
        request.session.clear()
        raise PermissionError("登录态失效")

    request.session["loggedIn"] = True
    return username, user_obj


def _safe_username_for_path(username: str) -> str:
    normalized = _normalize_text(username)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", normalized)
    return safe or "anonymous"


def _resolve_path_under_data(candidate: Path) -> Path | None:
    try:
        resolved = candidate.resolve()
    except OSError:
        return None

    data_root = DATA_DIR.resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError:
        return None

    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _resolve_avatar_path(user_obj: dict[str, Any], username: str = "") -> Path | None:
    raw_path = _normalize_text(user_obj.get("avatar"))
    safe_username = _safe_username_for_path(username)
    candidates: list[Path] = []

    if raw_path:
        normalized = raw_path.replace("\\", "/").lstrip("/")
        relative = Path(normalized)
        if relative.parts and relative.parts[0].lower() == "data":
            relative = Path(*relative.parts[1:]) if len(relative.parts) > 1 else Path()

        if str(relative):
            candidates.append(DATA_DIR / relative)
            candidates.append(BASE_DIR / relative)

            if len(relative.parts) == 1:
                filename = relative.name
                candidates.append(AVATAR_ROOT_DIR / safe_username / filename)
                candidates.append(LEGACY_AVATAR_DIR / filename)

    candidates.append(AVATAR_ROOT_DIR / safe_username / "avatar.png")
    candidates.append(LEGACY_AVATAR_DIR / f"{safe_username}.png")

    for candidate in candidates:
        resolved = _resolve_path_under_data(candidate)
        if resolved:
            return resolved

    return None


def _guess_image_media_type(path: Path) -> str:
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type and media_type.startswith("image/"):
        return media_type
    return "image/png"


def _default_avatar_svg(username: str) -> str:
    initial = (username.strip()[:1] or "U").upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#dbeafe"/>'
        '<stop offset="100%" stop-color="#bfdbfe"/>'
        "</linearGradient></defs>"
        '<rect width="320" height="320" rx="44" fill="url(#g)"/>'
        '<circle cx="160" cy="124" r="56" fill="#93c5fd"/>'
        '<rect x="74" y="204" width="172" height="84" rx="42" fill="#60a5fa"/>'
        f'<text x="160" y="182" text-anchor="middle" font-size="88" font-family="Arial, sans-serif" fill="#1e3a8a">{initial}</text>'
        "</svg>"
    )


def _convert_avatar_to_png(raw: bytes) -> bytes:
    if not raw:
        raise ValueError("上传文件为空")
    if len(raw) > _MAX_AVATAR_UPLOAD_BYTES:
        raise ValueError("头像文件过大，限制 5MB")

    try:
        with Image.open(BytesIO(raw)) as image:
            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            converted = image.convert("RGBA" if has_alpha else "RGB")
            output = BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()
    except UnidentifiedImageError as exc:
        raise ValueError("仅支持有效图片文件") from exc
    except OSError as exc:
        raise ValueError("图片解析失败") from exc


class LoginBody(BaseModel):
    username: str
    password: str


class RegisterBody(BaseModel):
    username: str
    password: str
    confirmPassword: str


class AddModelOptionBody(BaseModel):
    scope: str
    name: str
    model: str | None = None
    apiEndpoint: str
    apiKey: str
    apiKeyEnv: str | None = ""
    systemPrompt: str | None = ""
    stream: bool = True
    temperature: float | None = None


@router.get("/api/auth/status")
async def auth_status(request: Request) -> dict[str, Any]:
    username = _get_session_username(request)
    logged_in = _get_session_logged_in(request) or bool(username)

    if not logged_in or not username:
        return {
            "loggedIn": False,
            "username": "",
            "message": "not logged in",
        }

    user_obj = get_user(username)
    if not user_obj:
        request.session.clear()
        return {
            "loggedIn": False,
            "username": "",
            "message": "session user missing",
        }

    request.session["loggedIn"] = True

    return {
        "loggedIn": True,
        "username": username,
        "message": "ok",
    }


@router.post("/api/auth/register")
async def auth_register(body: RegisterBody) -> JSONResponse:
    username = _normalize_text(body.username)
    password = body.password or ""
    confirm_password = body.confirmPassword or ""

    if not _valid_username(username):
        return _json_error(
            400,
            "用户名需为 3-32 位，仅允许字母/数字/下划线",
        )

    if not _valid_password(password):
        return _json_error(400, "密码长度需为 6-72 位")

    if password != confirm_password:
        return _json_error(400, "两次密码不一致")

    salt_hex, password_hash = _hash_password(password)
    try:
        create_user(
            username=username,
            password_salt=salt_hex,
            password_hash=password_hash,
            bio=f"你好，{username}！欢迎使用灵·诊。",
            avatar="",
            links=[],
        )
    except ValueError as exc:
        return _json_error(409, str(exc))

    return JSONResponse(
        content={
            "success": True,
            "message": "注册成功",
            "loggedIn": False,
        },
    )


@router.post("/api/auth/login")
async def auth_login(body: LoginBody, request: Request) -> JSONResponse:
    username = _normalize_text(body.username)
    password = body.password or ""

    if not username or not password:
        return _json_error(400, "用户名和密码不能为空")

    user_obj = get_user(username)
    if not user_obj:
        return _json_error(401, "用户名或密码错误")

    salt_hex = _normalize_text(user_obj.get("passwordSalt"))
    password_hash = _normalize_text(user_obj.get("passwordHash"))

    if not salt_hex or not password_hash:
        return _json_error(500, "用户密码数据损坏")

    if not _verify_password(password, salt_hex, password_hash):
        return _json_error(401, "用户名或密码错误")

    request.session["username"] = username
    request.session["loggedIn"] = True

    return JSONResponse(
        content={
            "success": True,
            "message": "登录成功",
            "username": username,
            "loggedIn": True,
        },
    )


@router.post("/api/auth/logout")
async def auth_logout(request: Request) -> JSONResponse:
    request.session.clear()
    return JSONResponse(
        content={
            "success": True,
            "message": "已退出登录",
            "loggedIn": False,
        },
    )


@router.get("/api/user/profile")
async def user_profile(request: Request) -> JSONResponse:
    try:
        username, user_obj = _get_authenticated_username(request)
    except PermissionError as exc:
        return _json_error(401, str(exc))

    bio = _normalize_text(user_obj.get("bio")) or f"你好，{username}！欢迎使用灵·诊。"

    links_raw = user_obj.get("links")
    links: list[dict[str, str]] = []
    if isinstance(links_raw, list):
        for item in links_raw:
            if not isinstance(item, dict):
                continue
            name = _normalize_text(item.get("name"))
            href = _normalize_text(item.get("href"))
            icon = _normalize_text(item.get("icon"))
            if not name or not href:
                continue
            record = {"name": name, "href": href}
            if icon:
                record["icon"] = icon
            links.append(record)

    payload = {
        "username": username,
        "bio": bio,
        "avatar": "/api/user/avatar",
        "links": links,
        "charts": _build_user_charts(username),
    }

    return JSONResponse(content=payload)


@router.get("/api/user/avatar")
async def get_user_avatar(request: Request) -> Response:
    username = _get_session_username(request)
    user_obj = get_user(username) if username else None

    if user_obj:
        avatar_path = _resolve_avatar_path(user_obj, username=username)
        if avatar_path:
            try:
                payload = avatar_path.read_bytes()
                return Response(
                    content=payload,
                    media_type=_guess_image_media_type(avatar_path),
                    headers={"Cache-Control": "no-store"},
                )
            except OSError:
                pass

    svg = _default_avatar_svg(username or "U")
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/user/avatar")
async def upload_user_avatar(request: Request, image: UploadFile = File(...)) -> JSONResponse:
    try:
        username, _ = _get_authenticated_username(request)
    except PermissionError as exc:
        return _json_error(401, str(exc))

    content_type = (image.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        return _json_error(400, "仅支持图片文件上传")

    raw = await image.read()
    try:
        png_bytes = _convert_avatar_to_png(raw)
    except ValueError as exc:
        return _json_error(400, str(exc))

    safe_username = _safe_username_for_path(username)
    user_avatar_dir = AVATAR_ROOT_DIR / safe_username
    user_avatar_dir.mkdir(parents=True, exist_ok=True)
    target_path = user_avatar_dir / "avatar.png"
    try:
        target_path.write_bytes(png_bytes)
    except OSError:
        return _json_error(500, "头像保存失败")

    update_user_avatar(username, f"data/avatar/{safe_username}/avatar.png")

    return JSONResponse(
        content={
            "success": True,
            "message": "头像上传成功",
            "avatar": "/api/user/avatar",
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/user/model-options")
async def add_user_model_option(request: Request, body: AddModelOptionBody) -> JSONResponse:
    try:
        username, _ = _get_authenticated_username(request)
    except PermissionError as exc:
        return _json_error(401, str(exc))

    scope = _normalize_text(body.scope).lower()
    if scope not in _ALLOWED_MODEL_SCOPES:
        return _json_error(400, "scope 仅支持 chat / mental / face")

    name = _normalize_text(body.name)
    model = _normalize_text(body.model) or name
    api_endpoint = _normalize_text(body.apiEndpoint)
    api_key = _normalize_text(body.apiKey)
    api_key_env = _normalize_text(body.apiKeyEnv)
    system_prompt = _normalize_text(body.systemPrompt)

    if not name:
        return _json_error(400, "模型名称不能为空")
    if not model:
        return _json_error(400, "模型标识不能为空")
    if not api_endpoint:
        return _json_error(400, "apiEndpoint 不能为空")
    if not api_endpoint.startswith("http://") and not api_endpoint.startswith("https://"):
        return _json_error(400, "apiEndpoint 必须以 http:// 或 https:// 开头")
    if not api_key:
        return _json_error(400, "apiKey 不能为空")

    temperature: float | None = None
    if body.temperature is not None:
        temperature = max(0.0, min(2.0, float(body.temperature)))

    try:
        upsert_user_model_option(
            username=username,
            scope=scope,
            name=name,
            model=model,
            api_endpoint=api_endpoint,
            api_key=api_key,
            api_key_env=api_key_env,
            system_prompt=system_prompt,
            stream=bool(body.stream),
            temperature=temperature,
        )
    except ValueError as exc:
        return _json_error(400, str(exc))

    return JSONResponse(
        content={
            "success": True,
            "message": "模型已保存",
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/health")
async def health() -> dict[str, Any]:
    return {"success": True, "message": "ok"}
