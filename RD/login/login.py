from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"

_PASSWORD_ITERATIONS = 120_000
_USER_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
_STORE_LOCK = Lock()


def _normalize_text(value: Any) -> str:
	return value.strip() if isinstance(value, str) else ""


def _ensure_store() -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	if not USERS_FILE.exists():
		USERS_FILE.write_text("{}", encoding="utf-8")


def _read_users_unlocked() -> dict[str, dict[str, Any]]:
	_ensure_store()
	raw = USERS_FILE.read_text(encoding="utf-8").strip() or "{}"
	try:
		parsed = json.loads(raw)
	except json.JSONDecodeError:
		parsed = {}

	if not isinstance(parsed, dict):
		return {}

	normalized: dict[str, dict[str, Any]] = {}
	for username, user_obj in parsed.items():
		if not isinstance(username, str) or not isinstance(user_obj, dict):
			continue
		normalized[username] = user_obj
	return normalized


def _write_users_unlocked(users: dict[str, dict[str, Any]]) -> None:
	_ensure_store()
	temp_path = USERS_FILE.with_suffix(".tmp")
	temp_path.write_text(
		json.dumps(users, ensure_ascii=False, indent=2),
		encoding="utf-8",
	)
	temp_path.replace(USERS_FILE)


def _get_user(username: str) -> dict[str, Any] | None:
	with _STORE_LOCK:
		users = _read_users_unlocked()
		user_obj = users.get(username)
		if not isinstance(user_obj, dict):
			return None
		return dict(user_obj)


def _create_user(username: str, password: str) -> None:
	with _STORE_LOCK:
		users = _read_users_unlocked()
		if username in users:
			raise ValueError("用户名已存在")

		salt_hex, password_hash = _hash_password(password)

		users[username] = {
			"passwordSalt": salt_hex,
			"passwordHash": password_hash,
			"bio": f"你好，{username}！欢迎使用灵·诊。",
			"avatar": "",
			"links": [],
		}

		_write_users_unlocked(users)


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


def _build_chart_points(seed: int, offset: int, amp: int) -> list[dict[str, int]]:
	points: list[dict[str, int]] = []
	for index in range(1, 7):
		y = offset + ((seed + index * 7) % amp)
		points.append({"x": index, "y": y})
	return points


def _load_score_points(category: str, username: str) -> list[dict[str, int]]:
	score_path = DATA_DIR / category / username / "socre.json"
	if not score_path.exists():
		return []

	try:
		raw = json.loads(score_path.read_text(encoding="utf-8") or "{}")
	except (OSError, json.JSONDecodeError):
		return []

	if not isinstance(raw, dict):
		return []

	records_raw = raw.get("records")
	if not isinstance(records_raw, list):
		return []

	temp: list[tuple[str, int]] = []
	for item in records_raw:
		if not isinstance(item, dict):
			continue
		time_text = _normalize_text(item.get("time"))
		score_value = item.get("score")
		numeric_score: int | None = None
		if isinstance(score_value, int):
			numeric_score = score_value
		elif isinstance(score_value, float):
			numeric_score = int(round(score_value))
		elif isinstance(score_value, str):
			try:
				numeric_score = int(round(float(score_value.strip())))
			except ValueError:
				numeric_score = None

		if numeric_score is None:
			continue

		numeric_score = max(0, min(100, numeric_score))
		temp.append((time_text, numeric_score))

	if not temp:
		return []

	temp.sort(key=lambda item: item[0])
	return [{"x": index + 1, "y": score} for index, (_, score) in enumerate(temp)]


def _build_user_charts(username: str) -> list[dict[str, Any]]:
	seed = sum(ord(char) for char in username)
	face_points = _load_score_points("face", username)
	tg_points = _load_score_points("tg", username)

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


class LoginBody(BaseModel):
	username: str
	password: str


class RegisterBody(BaseModel):
	username: str
	password: str
	confirmPassword: str


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

	user_obj = _get_user(username)
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

	try:
		_create_user(username, password)
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

	user_obj = _get_user(username)
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
	username = _get_session_username(request)
	logged_in = _get_session_logged_in(request) or bool(username)

	if not logged_in or not username:
		return _json_error(401, "未登录")

	user_obj = _get_user(username)
	if not user_obj:
		request.session.clear()
		return _json_error(401, "登录态失效")

	bio = _normalize_text(user_obj.get("bio")) or f"你好，{username}！欢迎使用灵·诊。"
	avatar = _normalize_text(user_obj.get("avatar"))

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
		"avatar": avatar,
		"links": links,
		"charts": _build_user_charts(username),
	}

	return JSONResponse(content=payload)


@router.get("/api/health")
async def health() -> dict[str, Any]:
	return {"success": True, "message": "ok"}
