from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

try:
	from PIL import Image, UnidentifiedImageError
except ImportError as exc:  # pragma: no cover
	raise RuntimeError("缺少依赖 Pillow，请先安装：pip install pillow") from exc

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
TG_DATA_DIR = BASE_DIR / "data" / "tg"
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _safe_username(username: str) -> str:
	normalized = (username or "").strip()
	if not normalized:
		return "guest"
	safe = re.sub(r"[^a-zA-Z0-9_-]", "_", normalized)
	safe = safe.strip("._")
	return safe or "guest"


def _get_session_username(request: Request) -> str:
	value = request.session.get("username")
	return value.strip() if isinstance(value, str) else ""


def _format_filename(now: datetime | None = None) -> str:
	current = now or datetime.now()
	return (
		f"{current.year % 100:02d}-{current.month:02d}-{current.day:02d}"
		f"T{current.hour:02d}-{current.minute:02d}"
	)


def _build_target_path(username: str) -> Path:
	user_dir = TG_DATA_DIR / username
	user_dir.mkdir(parents=True, exist_ok=True)
	return user_dir / f"{_format_filename()}.png"


def _convert_to_png(raw: bytes) -> bytes:
	if not raw:
		raise HTTPException(status_code=400, detail="上传文件为空")
	if len(raw) > _MAX_UPLOAD_BYTES:
		raise HTTPException(status_code=413, detail="图片过大，限制 10MB")

	try:
		with Image.open(BytesIO(raw)) as img:
			has_alpha = img.mode in {"RGBA", "LA"} or (
				img.mode == "P" and "transparency" in img.info
			)
			converted = img.convert("RGBA" if has_alpha else "RGB")
			out = BytesIO()
			converted.save(out, format="PNG")
			return out.getvalue()
	except UnidentifiedImageError as exc:
		raise HTTPException(status_code=400, detail="仅支持有效图片文件") from exc
	except OSError as exc:
		raise HTTPException(status_code=400, detail="图片解析失败") from exc


@router.post("/api/tg/upload")
async def upload_tg_image(request: Request, image: UploadFile = File(...)) -> JSONResponse:
	content_type = (image.content_type or "").lower()
	if content_type and not content_type.startswith("image/"):
		raise HTTPException(status_code=400, detail="仅支持图片文件上传")

	raw = await image.read()
	png_bytes = _convert_to_png(raw)

	username = _safe_username(_get_session_username(request))
	target_path = _build_target_path(username)
	target_path.write_bytes(png_bytes)

	return JSONResponse(
		content={
			"success": True,
			"username": username,
			"filename": target_path.name,
			"relativePath": f"data/tg/{username}/{target_path.name}",
			"size": len(png_bytes),
		},
		headers={"Cache-Control": "no-store"},
	)
