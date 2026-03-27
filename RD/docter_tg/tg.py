from __future__ import annotations

import json
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

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


def _build_result_paths(user_dir: Path) -> tuple[str, Path, Path, Path]:
	base_stem = _format_filename()
	stem = base_stem
	suffix = 1
	while (user_dir / stem).exists():
		stem = f"{base_stem}-{suffix}"
		suffix += 1
	record_dir = user_dir / stem
	return stem, record_dir, record_dir / f"{stem}.json", record_dir / f"{stem}.png"


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


def _write_tg_result(
	record_stem: str,
	record_dir: Path,
	json_path: Path,
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
) -> tuple[str, str]:
	record_dir.mkdir(parents=True, exist_ok=True)
	image_path.write_bytes(image_bytes)
	relative_image_path = f"data/tg/{username}/{record_stem}/{image_path.name}"
	relative_json_path = f"data/tg/{username}/{record_stem}/{json_path.name}"
	color, spirit = _extract_result_fields(color_spirit_text)
	tongue_quality = _extract_tongue_quality(tongue_quality_text)
	hu_tongue_color = _extract_hu_tongue_color(hu_tongue_color_text)
	hu_tongue_coat = _extract_hu_tongue_coat(hu_tongue_coat_text)
	combined_raw_text = "\n".join([
		color_spirit_text.strip(),
		tongue_quality_text.strip(),
		hu_tongue_color_text.strip(),
		hu_tongue_coat_text.strip(),
		tizhi_score_text.strip(),
	]).strip()
	payload = {
		"recordName": record_stem,
		"owner": username,
		"updatedAt": datetime.now().isoformat(),
		"imagePath": relative_image_path,
		"tgData": {
			"color": color,
			"spirit": spirit,
			"tongueQuality": tongue_quality,
			"tongueColor": hu_tongue_color,
			"tongueCoatStatus": hu_tongue_coat,
			"tizhiScore": tizhi_score,
			"tizhiScoreSource": tizhi_score_source,
			"rawText": combined_raw_text,
			"colorSpiritText": color_spirit_text,
			"tongueQualityText": tongue_quality_text,
			"tongueColorText": hu_tongue_color_text,
			"tongueCoatText": hu_tongue_coat_text,
			"tizhiScoreText": tizhi_score_text,
		},
	}
	temp_path = json_path.with_suffix(".tmp")
	temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
	temp_path.replace(json_path)
	return relative_image_path, relative_json_path


def _resolve_record_dir(user_dir: Path, record_name: str) -> Path:
	name = record_name.strip()
	if not TG_RECORD_STEM_PATTERN.fullmatch(name):
		raise HTTPException(status_code=400, detail="记录名称不合法")
	record_dir = user_dir / name
	if not record_dir.exists() or not record_dir.is_dir():
		raise HTTPException(status_code=404, detail="记录不存在")
	return record_dir


def _list_record_names(user_dir: Path) -> list[str]:
	if not user_dir.exists():
		return []
	result: list[str] = []
	for child in user_dir.iterdir():
		if not child.is_dir():
			continue
		name = child.name
		if not TG_RECORD_STEM_PATTERN.fullmatch(name):
			continue
		if (child / f"{name}.json").exists():
			result.append(name)
	return sorted(result, reverse=True)


@router.get("/api/tg/history")
async def tg_history(
	request: Request,
	action: str = Query(default="list"),
	name: str | None = Query(default=None),
):
	username = _safe_username(_get_session_username(request))
	user_dir = TG_DATA_DIR / username

	if action == "list":
		return JSONResponse(content={"records": _list_record_names(user_dir)})

	if not name:
		raise HTTPException(status_code=400, detail="缺少记录名称")

	record_dir = _resolve_record_dir(user_dir, name)
	record_name = record_dir.name
	json_path = record_dir / f"{record_name}.json"
	image_path = record_dir / f"{record_name}.png"

	if action == "load":
		if not json_path.exists():
			raise HTTPException(status_code=404, detail="记录文件不存在")
		try:
			payload = json.loads(json_path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError) as exc:
			raise HTTPException(status_code=500, detail="记录文件读取失败") from exc
		if not isinstance(payload, dict):
			raise HTTPException(status_code=500, detail="记录文件格式错误")
		return JSONResponse(content=payload)

	if action == "image":
		if not image_path.exists():
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
	record_stem, record_dir, json_path, image_path = _build_result_paths(user_dir)
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

	relative_image_path, relative_json_path = _write_tg_result(
		record_stem=record_stem,
		record_dir=record_dir,
		json_path=json_path,
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
			"resultFile": relative_json_path,
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
