from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from urllib import error as url_error
from urllib import request as url_request

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from PIL import Image, UnidentifiedImageError

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
FACE_DIR = Path(__file__).resolve().parent
FACE_DATA_DIR = BASE_DIR / "data" / "face"
CONFIG_PATH = FACE_DIR / "api.json"
PROMPT_PATH = FACE_DIR / "prompt.md"
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_STORE_LOCK = Lock()


@dataclass
class ModelOption:
	name: str
	model: str
	api_endpoint: str
	api_key: str
	api_key_env: str
	stream: bool
	temperature: float | None


def _read_text_file(path: Path) -> str:
	if not path.exists():
		return ""
	return path.read_text(encoding="utf-8").strip()


def _load_env_map() -> dict[str, str]:
	env_map: dict[str, str] = {}
	for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
		if not env_path.exists():
			continue
		try:
			for raw_line in env_path.read_text(encoding="utf-8").splitlines():
				line = raw_line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue
				key, value = line.split("=", 1)
				key = key.strip()
				value = value.strip().strip('"').strip("'")
				if key and key not in env_map:
					env_map[key] = value
		except OSError:
			continue
	return env_map


def _normalize_api_endpoint(endpoint: str) -> str:
	value = endpoint.strip()
	if not value:
		return value

	if re.match(r"^https://api\.deepseek\.com/?$", value, flags=re.IGNORECASE):
		return "https://api.deepseek.com/chat/completions"
	if re.match(r"^https://models\.github\.ai/inference/?$", value, flags=re.IGNORECASE):
		return "https://models.github.ai/inference/chat/completions"

	normalized = value.rstrip("/")
	if re.search(r"/v1$", normalized, flags=re.IGNORECASE):
		return f"{normalized}/chat/completions"
	if re.search(r"/chat/completions$", normalized, flags=re.IGNORECASE):
		return normalized

	return value


def _to_bool(value: Any, default: bool = False) -> bool:
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return bool(value)
	if isinstance(value, str):
		lowered = value.strip().lower()
		if lowered in {"1", "true", "yes", "on"}:
			return True
		if lowered in {"0", "false", "no", "off"}:
			return False
	return default


def _to_optional_float(value: Any) -> float | None:
	if value is None:
		return None
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return None
		try:
			return float(text)
		except ValueError:
			return None
	return None


def _load_face_config_raw() -> dict[str, Any]:
	if not CONFIG_PATH.exists():
		return {}
	try:
		data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
		if isinstance(data, dict):
			return data
	except (OSError, json.JSONDecodeError):
		return {}
	return {}


def _normalize_model_options(raw: dict[str, Any]) -> list[ModelOption]:
	options = raw.get("modelOptions") if isinstance(raw.get("modelOptions"), list) else []

	fallback_api_endpoint = _normalize_api_endpoint(str(raw.get("apiEndpoint") or "").strip())
	fallback_api_key = str(raw.get("apiKey") or "").strip()
	fallback_api_key_env = str(raw.get("apiKeyEnv") or "").strip()
	fallback_model = str(raw.get("model") or "").strip()
	fallback_stream = _to_bool(raw.get("stream"), default=True)
	fallback_temperature = _to_optional_float(raw.get("temperature"))

	normalized: list[ModelOption] = []
	for option in options:
		if isinstance(option, str):
			name = option.strip()
			if not name:
				continue
			normalized.append(
				ModelOption(
					name=name,
					model=name,
					api_endpoint=fallback_api_endpoint,
					api_key=fallback_api_key,
					api_key_env=fallback_api_key_env,
					stream=fallback_stream,
					temperature=fallback_temperature,
				)
			)
			continue

		if not isinstance(option, dict):
			continue

		model = str(option.get("model") or "").strip()
		name = str(option.get("name") or option.get("label") or model).strip()
		api_endpoint = _normalize_api_endpoint(str(option.get("apiEndpoint") or fallback_api_endpoint).strip())
		api_key = str(option.get("apiKey") or fallback_api_key).strip()
		api_key_env = str(option.get("apiKeyEnv") or fallback_api_key_env).strip()
		stream = _to_bool(option.get("stream"), default=fallback_stream)
		temperature = _to_optional_float(option.get("temperature") if "temperature" in option else fallback_temperature)

		if not name or not model or not api_endpoint:
			continue

		normalized.append(
			ModelOption(
				name=name,
				model=model,
				api_endpoint=api_endpoint,
				api_key=api_key,
				api_key_env=api_key_env,
				stream=stream,
				temperature=temperature,
			)
		)

	dedup: dict[str, ModelOption] = {}
	for item in normalized:
		if item.name not in dedup:
			dedup[item.name] = item

	result = list(dedup.values())
	if not result and fallback_model and fallback_api_endpoint:
		result.append(
			ModelOption(
				name=fallback_model,
				model=fallback_model,
				api_endpoint=fallback_api_endpoint,
				api_key=fallback_api_key,
				api_key_env=fallback_api_key_env,
				stream=fallback_stream,
				temperature=fallback_temperature,
			)
		)
	return result


def _resolve_option(raw: dict[str, Any], selected_name: str | None) -> ModelOption | None:
	options = _normalize_model_options(raw)
	preferred_name = (selected_name or "").strip()
	config_selected_name = str(raw.get("selectedOptionName") or "").strip()

	if preferred_name:
		hit = next((item for item in options if item.name == preferred_name), None)
		if hit is not None:
			return hit

	if config_selected_name:
		hit = next((item for item in options if item.name == config_selected_name), None)
		if hit is not None:
			return hit

	return options[0] if options else None


def _resolve_api_key(api_key_env: str, api_key: str, env_map: dict[str, str]) -> str:
	env_name = api_key_env.strip()
	if env_name:
		value = os.getenv(env_name) or env_map.get(env_name, "")
		if isinstance(value, str) and value.strip():
			return value.strip()
	return api_key.strip()


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


def _get_user_face_dir(request: Request) -> tuple[str, Path]:
	username = _safe_username(_get_session_username(request))
	directory = FACE_DATA_DIR / username
	directory.mkdir(parents=True, exist_ok=True)
	return username, directory


def _format_result_filename(now: datetime | None = None) -> str:
	current = now or datetime.now()
	return (
		f"face-{current.year % 100:02d}-{current.month:02d}-{current.day:02d}"
		f"T{current.hour:02d}-{current.minute:02d}.json"
	)


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


def _is_ollama_endpoint(endpoint: str) -> bool:
	endpoint_lower = endpoint.lower()
	return "127.0.0.1:11434" in endpoint_lower or "localhost:11434" in endpoint_lower


def _extract_model_not_found(error_text: str) -> str | None:
	match = re.search(r"model '([^']+)' not found", error_text, flags=re.IGNORECASE)
	return match.group(1) if match else None


def _http_json_request(
	url: str,
	method: str,
	payload: dict[str, Any] | None,
	headers: dict[str, str],
	timeout: int = 120,
) -> tuple[int, str, str]:
	data = None
	if payload is not None:
		data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

	req = url_request.Request(url=url, method=method, data=data, headers=headers)
	try:
		with url_request.urlopen(req, timeout=timeout) as resp:
			content_type = str(resp.headers.get("Content-Type") or "")
			text = resp.read().decode("utf-8", errors="replace")
			return int(resp.status), content_type, text
	except url_error.HTTPError as exc:
		content_type = str(exc.headers.get("Content-Type") or "") if exc.headers else ""
		body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
		return int(exc.code), content_type, body
	except url_error.URLError as exc:
		raise HTTPException(status_code=502, detail=f"上游接口不可达：{exc.reason}") from exc


def _find_best_ollama_model(requested_model: str, candidates: list[str]) -> str | None:
	if not requested_model or not candidates:
		return None
	requested_lower = requested_model.lower()

	exact = next((item for item in candidates if item.lower() == requested_lower), None)
	if exact:
		return exact

	prefix = next((item for item in candidates if item.lower().startswith(requested_lower)), None)
	if prefix:
		return prefix

	family = requested_lower.split(":")[0]
	family_match = next((item for item in candidates if item.lower().startswith(f"{family}:")), None)
	if family_match:
		return family_match

	return None


def _resolve_ollama_model_name(api_endpoint: str, requested_model: str) -> str | None:
	match = re.match(r"^(https?://[^/]+)", api_endpoint.strip(), flags=re.IGNORECASE)
	if not match:
		return None
	tags_endpoint = f"{match.group(1)}/api/tags"

	try:
		status, _, body = _http_json_request(
			url=tags_endpoint,
			method="GET",
			payload=None,
			headers={"Cache-Control": "no-store"},
			timeout=20,
		)
		if status < 200 or status >= 300:
			return None
		payload = json.loads(body)
		models = payload.get("models") if isinstance(payload, dict) else []
		names: list[str] = []
		if isinstance(models, list):
			for item in models:
				if not isinstance(item, dict):
					continue
				name = str(item.get("name") or item.get("model") or "").strip()
				if name:
					names.append(name)
		return _find_best_ollama_model(requested_model, names)
	except (json.JSONDecodeError, HTTPException):
		return None


def _extract_text_from_payload(payload: Any) -> str:
	if isinstance(payload, str):
		return payload
	if not isinstance(payload, dict):
		return ""

	message = payload.get("message")
	if isinstance(message, dict):
		content = message.get("content")
		if isinstance(content, str):
			return content

	response_text = payload.get("response")
	if isinstance(response_text, str):
		return response_text

	choices = payload.get("choices")
	if isinstance(choices, list) and choices:
		first = choices[0]
		if isinstance(first, dict):
			delta = first.get("delta")
			if isinstance(delta, dict):
				delta_content = delta.get("content")
				if isinstance(delta_content, str):
					return delta_content
			choice_message = first.get("message")
			if isinstance(choice_message, dict):
				choice_content = choice_message.get("content")
				if isinstance(choice_content, str):
					return choice_content
			choice_text = first.get("text")
			if isinstance(choice_text, str):
				return choice_text

	return ""


def _consume_stream_buffer(buffer: str, final: bool = False) -> tuple[str, str]:
	if not buffer:
		return "", ""

	lines = buffer.splitlines(keepends=True)
	rest = ""
	if not final and lines and not lines[-1].endswith("\n"):
		rest = lines.pop()

	parts: list[str] = []
	for line in lines:
		text = line.strip()
		if not text:
			continue

		payload_text = text
		if text.startswith("data:"):
			payload_text = text[5:].strip()
			if payload_text == "[DONE]":
				continue

		try:
			payload = json.loads(payload_text)
			extracted = _extract_text_from_payload(payload)
			if extracted:
				parts.append(extracted)
			continue
		except json.JSONDecodeError:
			if not text.startswith("data:"):
				parts.append(text)

	return "".join(parts), rest


def _build_upstream_messages(prompt_text: str, image_b64: str, use_ollama: bool) -> list[dict[str, Any]]:
	clean_prompt = prompt_text.strip()
	user_text = "请根据这张面部图片，按要求输出面部观察数据。"

	if use_ollama:
		messages: list[dict[str, Any]] = []
		if clean_prompt:
			messages.append({"role": "system", "content": clean_prompt})
		messages.append({"role": "user", "content": user_text, "images": [image_b64]})
		return messages

	user_content: list[dict[str, Any]] = [
		{"type": "text", "text": user_text},
		{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
	]

	messages = []
	if clean_prompt:
		messages.append({"role": "system", "content": clean_prompt})
	messages.append({"role": "user", "content": user_content})
	return messages


def _build_upstream_payload(
	target_model: str,
	payload_messages: list[dict[str, Any]],
	stream: bool,
	temperature: float | None,
) -> dict[str, Any]:
	payload: dict[str, Any] = {
		"model": target_model,
		"messages": payload_messages,
		"stream": stream,
	}
	if temperature is not None:
		payload["temperature"] = temperature
	return payload


def _parse_face_data(text: str) -> dict[str, Any]:
	stripped = text.strip()
	if not stripped:
		return {"rawText": ""}
	try:
		parsed = json.loads(stripped)
		if isinstance(parsed, dict):
			return parsed
		if isinstance(parsed, list):
			return {"items": parsed}
		return {"value": parsed}
	except json.JSONDecodeError:
		return {"rawText": stripped}


def _write_face_result(
	target_path: Path,
	username: str,
	model_name: str,
	selected_option_name: str,
	prompt_text: str,
	output_text: str,
) -> None:
	payload = {
		"recordName": target_path.stem,
		"owner": username,
		"updatedAt": datetime.now().isoformat(),
		"model": model_name,
		"selectedOptionName": selected_option_name,
		"prompt": prompt_text,
		"faceData": _parse_face_data(output_text),
	}
	temp_path = target_path.with_suffix(".tmp")
	temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
	temp_path.replace(target_path)


@router.post("/api/face/doc")
async def stream_face_doc(
	request: Request,
	image: UploadFile = File(...),
	selectedOptionName: str | None = Form(default=None),
	temperature: float | None = Form(default=None),
) -> Response:
	content_type = (image.content_type or "").lower()
	if content_type and not content_type.startswith("image/"):
		return JSONResponse(status_code=400, content={"error": "仅支持图片文件上传"})

	raw = await image.read()
	png_bytes = _convert_to_png(raw)
	image_b64 = base64.b64encode(png_bytes).decode("utf-8")

	raw_config = _load_face_config_raw()
	resolved = _resolve_option(raw_config, selectedOptionName)
	if resolved is None or not resolved.api_endpoint or not resolved.model:
		return JSONResponse(status_code=500, content={"error": "RD/doctor_face/api.json 配置不完整"})

	prompt_text = _read_text_file(PROMPT_PATH)
	env_map = _load_env_map()
	api_key = _resolve_api_key(resolved.api_key_env, resolved.api_key, env_map)
	if resolved.api_key_env and not api_key:
		return JSONResponse(
			status_code=500,
			content={"error": f"环境变量 {resolved.api_key_env} 未设置，请在 .env 中配置后重启服务"},
		)

	headers = {"Content-Type": "application/json"}
	if api_key:
		headers["Authorization"] = f"Bearer {api_key}"

	requested_temperature = temperature if temperature is not None else resolved.temperature
	if requested_temperature is not None:
		requested_temperature = max(0.0, min(2.0, float(requested_temperature)))

	payload_messages = _build_upstream_messages(
		prompt_text=prompt_text,
		image_b64=image_b64,
		use_ollama=_is_ollama_endpoint(resolved.api_endpoint),
	)

	def open_upstream_stream(target_model: str) -> tuple[Any | None, int, str, str]:
		req = url_request.Request(
			url=resolved.api_endpoint,
			method="POST",
			data=json.dumps(
				_build_upstream_payload(
					target_model=target_model,
					payload_messages=payload_messages,
					stream=True,
					temperature=requested_temperature,
				),
				ensure_ascii=False,
			).encode("utf-8"),
			headers=headers,
		)

		try:
			response = url_request.urlopen(req, timeout=240)
			return response, int(response.status), str(response.headers.get("Content-Type") or ""), ""
		except url_error.HTTPError as exc:
			content_type_error = str(exc.headers.get("Content-Type") or "") if exc.headers else ""
			body_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
			return None, int(exc.code), content_type_error, body_text
		except url_error.URLError as exc:
			raise HTTPException(status_code=502, detail=f"上游接口不可达：{exc.reason}") from exc

	active_model = resolved.model
	stream_response, status_code, _, error_text = open_upstream_stream(active_model)
	if stream_response is None:
		missing_model = _extract_model_not_found(error_text)
		if status_code == 404 and missing_model and _is_ollama_endpoint(resolved.api_endpoint):
			retry_model = _resolve_ollama_model_name(resolved.api_endpoint, missing_model)
			if retry_model and retry_model != active_model:
				active_model = retry_model
				stream_response, status_code, _, error_text = open_upstream_stream(active_model)

	if stream_response is None:
		return Response(
			content=error_text or "上游接口请求失败",
			status_code=status_code,
			media_type="text/plain; charset=utf-8",
		)

	username, user_dir = _get_user_face_dir(request)
	target_path = user_dir / _format_result_filename()

	def plain_text_stream():
		pieces: list[str] = []
		try:
			buffer = ""
			while True:
				chunk = stream_response.read(1024)
				if not chunk:
					break
				buffer += chunk.decode("utf-8", errors="ignore")
				output, buffer = _consume_stream_buffer(buffer, final=False)
				if output:
					pieces.append(output)
					yield output

			tail, _ = _consume_stream_buffer(buffer, final=True)
			if tail:
				pieces.append(tail)
				yield tail
		finally:
			try:
				stream_response.close()
			except Exception:
				pass

			final_text = "".join(pieces)
			with _STORE_LOCK:
				_write_face_result(
					target_path=target_path,
					username=username,
					model_name=active_model,
					selected_option_name=resolved.name,
					prompt_text=prompt_text,
					output_text=final_text,
				)

	return StreamingResponse(
		plain_text_stream(),
		media_type="text/plain; charset=utf-8",
		headers={
			"Cache-Control": "no-store",
			"X-Resolved-Model": active_model,
			"X-Result-File": f"data/face/{username}/{target_path.name}",
			"X-Stream-Enabled": "true",
		},
	)
