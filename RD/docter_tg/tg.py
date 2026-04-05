from __future__ import annotations

import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from storage.db import (
	get_diagnosis_record,
	list_diagnosis_record_names,
	save_diagnosis_record,
)

from .ay_color_sprit import predict_color_spirit
from .hu import predict_hu_tongue
from .tg_socre import append_tg_socre, score_tg_tizhi
from .yzp import predict_tongue_quality

try:
	from PIL import Image, UnidentifiedImageError
except ImportError as exc:  # pragma: no cover
	raise RuntimeError("缺少依赖 Pillow，请先安装：pip install pillow") from exc

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
TG_DATA_DIR = BASE_DIR / "data" / "tg"
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_TG_MODEL_DIR = Path(__file__).resolve().parent / "ay_color_sprit"
TG_RECORD_STEM_PATTERN = re.compile(r"^tg-\d{2}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d+)?$")
TG_SCOPE = "tg"


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
		f"tg-{current.year % 100:02d}-{current.month:02d}-{current.day:02d}"
		f"T{current.hour:02d}-{current.minute:02d}"
	)


def _get_user_tg_dir(request: Request) -> tuple[str, Path]:
	username = _safe_username(_get_session_username(request))
	directory = TG_DATA_DIR / username
	directory.mkdir(parents=True, exist_ok=True)
	return username, directory


def _build_result_paths(user_dir: Path) -> tuple[str, Path, Path]:
	base_stem = _format_filename()
	stem = base_stem
	suffix = 1
	while (user_dir / stem).exists():
		stem = f"{base_stem}-{suffix}"
		suffix += 1
	record_dir = user_dir / stem
	return stem, record_dir, record_dir / f"{stem}.png"


def _extract_result_fields(result_text: str) -> tuple[str, str]:
	color = ""
	spirit = ""
	for line in result_text.splitlines():
		stripped = line.strip()
		if stripped.startswith("【苔色】："):
			color = stripped.replace("【苔色】：", "", 1).strip()
		elif stripped.startswith("【舌神】："):
			spirit = stripped.replace("【舌神】：", "", 1).strip()
	return color, spirit


def _extract_tongue_quality(result_text: str) -> str:
	for line in result_text.splitlines():
		stripped = line.strip()
		if stripped.startswith("[苔质类型]："):
			return stripped.replace("[苔质类型]：", "", 1).strip()
	return ""


def _extract_hu_tongue_color(result_text: str) -> str:
	for line in result_text.splitlines():
		stripped = line.strip()
		if stripped.startswith("【舌色结果】："):
			return stripped.replace("【舌色结果】：", "", 1).strip()
	return ""


def _extract_hu_tongue_coat(result_text: str) -> str:
	for line in result_text.splitlines():
		stripped = line.strip()
		if stripped.startswith("【舌苔状态】："):
			return stripped.replace("【舌苔状态】：", "", 1).strip()
	return ""


def _resolve_data_file_path(raw_path: str) -> Path | None:
	value = (raw_path or "").strip()
	if not value:
		return None

	candidate = BASE_DIR / value.replace("\\", "/").lstrip("/")
	try:
		resolved = candidate.resolve()
	except OSError:
		return None

	data_root = (BASE_DIR / "data").resolve()
	try:
		resolved.relative_to(data_root)
	except ValueError:
		return None

	if not resolved.exists() or not resolved.is_file():
		return None

	return resolved


def _write_tg_result(
	record_stem: str,
	record_dir: Path,
	image_path: Path,
	image_bytes: bytes,
	username: str,
	color_spirit_text: str,
	tongue_quality_text: str,
	hu_tongue_color_text: str,
	hu_tongue_coat_text: str,
	tizhi_score: int | None = None,
	tizhi_score_text: str = "",
	tizhi_score_source: str = "fallback",
) -> str:
	record_dir.mkdir(parents=True, exist_ok=True)
	image_path.write_bytes(image_bytes)
	relative_image_path = f"data/tg/{username}/{record_stem}/{image_path.name}"
	return relative_image_path


def _list_record_names(username: str) -> list[str]:
	return list_diagnosis_record_names(username, TG_SCOPE)


@router.get("/api/tg/history")
async def tg_history(
	request: Request,
	action: str = Query(default="list"),
	name: str | None = Query(default=None),
):
	username = _safe_username(_get_session_username(request))

	if action == "list":
		return JSONResponse(content={"records": _list_record_names(username)})

	if not name:
		raise HTTPException(status_code=400, detail="缺少记录名称")

	record_name = name.strip()
	if not TG_RECORD_STEM_PATTERN.fullmatch(record_name):
		raise HTTPException(status_code=400, detail="记录名称不合法")

	record = get_diagnosis_record(username, TG_SCOPE, record_name)
	if not record:
		raise HTTPException(status_code=404, detail="记录不存在")

	if action == "load":
		payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
		if not payload:
			payload = {
				"recordName": record_name,
				"imagePath": record.get("imagePath") or "",
				"tgData": {"rawText": record.get("resultText") or ""},
			}
		return JSONResponse(content=payload)

	if action == "image":
		image_path = _resolve_data_file_path(str(record.get("imagePath") or ""))
		if not image_path:
			raise HTTPException(status_code=404, detail="记录图片不存在")
		return FileResponse(path=image_path, media_type="image/png")

	raise HTTPException(status_code=400, detail="不支持的动作")


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

	username, user_dir = _get_user_tg_dir(request)
	record_stem, record_dir, image_path = _build_result_paths(user_dir)
	record_dir.mkdir(parents=True, exist_ok=True)
	image_path.write_bytes(png_bytes)

	try:
		color_spirit_text = predict_color_spirit(
			img_path=image_path,
			color_model_path=_TG_MODEL_DIR / "color_model.pt",
			spirit_model_path=_TG_MODEL_DIR / "spirit_model.pt",
		)
		tongue_quality_text = predict_tongue_quality(
			img_path=image_path,
			model_path=Path(__file__).resolve().parent / "yzp" / "tongue_classifier.pth",
		)
		hu_tongue_color_text, hu_tongue_coat_text = predict_hu_tongue(
			img_path=image_path,
		)
	except Exception as exc:
		raise HTTPException(status_code=500, detail=f"舌诊结果生成失败：{exc}") from exc

	score_source_text = "\n".join([
		color_spirit_text.strip(),
		tongue_quality_text.strip(),
		hu_tongue_color_text.strip(),
		hu_tongue_coat_text.strip(),
	]).strip()

	time.sleep(5)
	tizhi_score, tizhi_score_line, is_llm_score = score_tg_tizhi(score_source_text)
	tizhi_score_source = "llm" if is_llm_score else "fallback"

	relative_image_path = _write_tg_result(
		record_stem=record_stem,
		record_dir=record_dir,
		image_path=image_path,
		image_bytes=png_bytes,
		username=username,
		color_spirit_text=color_spirit_text,
		tongue_quality_text=tongue_quality_text,
		hu_tongue_color_text=hu_tongue_color_text,
		hu_tongue_coat_text=hu_tongue_coat_text,
		tizhi_score=tizhi_score,
		tizhi_score_text=tizhi_score_line,
		tizhi_score_source=tizhi_score_source,
	)

	tg_payload = {
		"recordName": record_stem,
		"owner": username,
		"imagePath": relative_image_path,
		"resultFile": f"db:tg/{record_stem}",
		"tgData": {
			"rawText": "\n".join([
				color_spirit_text.strip(),
				tongue_quality_text.strip(),
				hu_tongue_color_text.strip(),
				hu_tongue_coat_text.strip(),
				tizhi_score_line.strip(),
			]).strip(),
			"colorSpiritText": color_spirit_text,
			"tongueQualityText": tongue_quality_text,
			"tongueColorText": hu_tongue_color_text,
			"tongueCoatText": hu_tongue_coat_text,
			"tizhiScore": tizhi_score,
			"tizhiScoreSource": tizhi_score_source,
			"tizhiScoreText": tizhi_score_line,
		},
	}
	save_diagnosis_record(
		username=username,
		scope=TG_SCOPE,
		record_name=record_stem,
		image_path=relative_image_path,
		result_text=tg_payload["tgData"]["rawText"],
		payload=tg_payload,
		score=tizhi_score,
		score_source=tizhi_score_source,
	)

	if tizhi_score is not None:
		append_tg_socre(
			username=username,
			record_name=record_stem,
			score=tizhi_score,
			score_source=tizhi_score_source,
		)

	result_text = "\n".join([
		color_spirit_text.strip(),
		tongue_quality_text.strip(),
		hu_tongue_color_text.strip(),
		hu_tongue_coat_text.strip(),
		tizhi_score_line.strip(),
	]).strip()

	return JSONResponse(
		content={
			"success": True,
			"username": username,
			"recordName": record_stem,
			"filename": image_path.name,
			"relativePath": relative_image_path,
			"resultFile": f"db:tg/{record_stem}",
			"resultText": result_text,
			"colorSpiritText": color_spirit_text,
			"tongueQualityText": tongue_quality_text,
			"tongueColorText": hu_tongue_color_text,
			"tongueCoatText": hu_tongue_coat_text,
			"tizhiScore": tizhi_score,
			"tizhiScoreSource": tizhi_score_source,
			"tizhiScoreText": tizhi_score_line,
			"size": len(png_bytes),
		},
		headers={"Cache-Control": "no-store"},
	)
