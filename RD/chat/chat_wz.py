from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib import error as url_error
from urllib import request as url_request

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
CHAT_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHAT_DATA_DIR = DATA_DIR / "chat"
FACE_DATA_DIR = DATA_DIR / "face"
CONFIG_PATH = CHAT_DIR / "api.json"
PROMPT_PATH = CHAT_DIR / "prompt.md"

_STORE_LOCK = Lock()

CHAT_RECORD_NAME_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?:-\d+)?$")
SAFE_RECORD_BASENAME_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d+)?$")
FACE_RECORD_STEM_PATTERN = re.compile(r"^face-\d{2}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d+)?$")


@dataclass
class ModelOption:
    name: str
    model: str
    api_endpoint: str
    api_key: str
    api_key_env: str
    system_prompt: str
    stream: bool
    temperature: float | None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    selectedOptionName: str | None = None
    messages: list[ChatMessage]
    stream: bool | None = None
    temperature: float | None = None


class SaveBody(BaseModel):
    recordName: str | None = None
    messages: list[ChatMessage]


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
    if re.match(r"^https://api\.deepseek\.com/?$", value, flags=re.IGNORECASE):
        return "https://api.deepseek.com/chat/completions"
    if re.match(r"^https://models\.github\.ai/inference/?$", value, flags=re.IGNORECASE):
        return "https://models.github.ai/inference/chat/completions"
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


def _load_chat_config_raw() -> dict[str, Any]:
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
    default_prompt = _read_text_file(PROMPT_PATH) or str(raw.get("systemPrompt") or "").strip()

    fallback_api_endpoint = _normalize_api_endpoint(str(raw.get("apiEndpoint") or "").strip())
    fallback_api_key = str(raw.get("apiKey") or "").strip()
    fallback_api_key_env = str(raw.get("apiKeyEnv") or "").strip()
    fallback_model = str(raw.get("model") or "").strip()
    fallback_stream = _to_bool(raw.get("stream"), default=False)
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
                    system_prompt=default_prompt,
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
        system_prompt = str(option.get("systemPrompt") or default_prompt).strip()
        stream = _to_bool(option.get("stream"), default=fallback_stream)
        temperature = _to_optional_float(
            option.get("temperature")
            if "temperature" in option
            else fallback_temperature
        )

        if not name or not model or not api_endpoint:
            continue

        normalized.append(
            ModelOption(
                name=name,
                model=model,
                api_endpoint=api_endpoint,
                api_key=api_key,
                api_key_env=api_key_env,
                system_prompt=system_prompt,
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
                system_prompt=default_prompt,
                stream=fallback_stream,
                temperature=fallback_temperature,
            )
        )

    return result


def _resolve_option(raw: dict[str, Any], selected_name: str | None) -> tuple[ModelOption | None, list[ModelOption]]:
    options = _normalize_model_options(raw)
    preferred_name = (selected_name or "").strip()
    config_selected_name = str(raw.get("selectedOptionName") or "").strip()

    resolved = None
    if preferred_name:
        resolved = next((item for item in options if item.name == preferred_name), None)
    if resolved is None and config_selected_name:
        resolved = next((item for item in options if item.name == config_selected_name), None)
    if resolved is None and options:
        resolved = options[0]

    return resolved, options


def _resolve_api_key(api_key_env: str, api_key: str, env_map: dict[str, str]) -> str:
    env_name = api_key_env.strip()
    if env_name:
        value = os.getenv(env_name) or env_map.get(env_name, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return api_key.strip()


def _normalize_persist_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = (message.role or "").strip()
        content = (message.content or "").strip()
        if role in ("user", "assistant") and content:
            normalized.append({"role": role, "content": content})
    return normalized


def _build_upstream_messages(messages: list[ChatMessage], system_prompt: str) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = (message.role or "").strip()
        content = (message.content or "").strip()
        if role not in ("system", "user", "assistant"):
            continue
        if not content:
            continue
        if role == "system":
            continue
        normalized.append({"role": role, "content": content})

    final_prompt = (system_prompt or "").strip()
    if final_prompt:
        return [{"role": "system", "content": final_prompt}, *normalized]
    return normalized


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


def _build_upstream_payload(
    target_model: str,
    payload_messages: list[dict[str, str]],
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


def _pad2(value: int) -> str:
    return str(value).zfill(2)


def _format_record_name(now: datetime | None = None) -> str:
    target = now or datetime.now()
    year = _pad2(target.year % 100)
    month = _pad2(target.month)
    day = _pad2(target.day)
    hour = _pad2(target.hour)
    minute = _pad2(target.minute)
    return f"{year}-{month}-{day}T{hour}:{minute}"


def _record_name_to_safe_basename(record_name: str) -> str:
    return record_name.replace(":", "-")


def _safe_basename_to_record_name(file_base_name: str) -> str | None:
    if CHAT_RECORD_NAME_PATTERN.match(file_base_name):
        return file_base_name

    if not SAFE_RECORD_BASENAME_PATTERN.match(file_base_name):
        return None

    match = re.match(r"^(\d{2}-\d{2}-\d{2}T\d{2})-(\d{2})(-\d+)?$", file_base_name)
    if not match:
        return None
    return f"{match.group(1)}:{match.group(2)}{match.group(3) or ''}"


def _sanitize_record_name(raw_name: str | None) -> str | None:
    name = (raw_name or "").strip()
    if not name:
        return None
    if not CHAT_RECORD_NAME_PATTERN.match(name):
        return None
    return name


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


def _get_user_records_dir(request: Request) -> Path:
    username = _safe_username(_get_session_username(request))
    directory = CHAT_DATA_DIR / username
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _get_user_face_dir(request: Request) -> Path:
    username = _safe_username(_get_session_username(request))
    directory = FACE_DATA_DIR / username
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _list_face_record_stems(face_dir: Path) -> list[str]:
    if not face_dir.exists():
        return []
    stems: list[str] = []
    for entry in face_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".json":
            continue
        stem = entry.stem.strip()
        if FACE_RECORD_STEM_PATTERN.match(stem):
            stems.append(stem)
    stems.sort(reverse=True)
    return stems


def _sanitize_face_record_stem(raw_name: str | None) -> str | None:
    name = (raw_name or "").strip()
    if not name:
        return None
    if not FACE_RECORD_STEM_PATTERN.match(name):
        return None
    return name


def _extract_face_prompt(face_data: Any) -> str:
    if isinstance(face_data, str):
        return face_data.strip()
    if isinstance(face_data, dict):
        raw_text = face_data.get("rawText")
        if isinstance(raw_text, str) and raw_text.strip():
            return raw_text.strip()
        try:
            return json.dumps(face_data, ensure_ascii=False)
        except TypeError:
            return str(face_data)
    if isinstance(face_data, list):
        try:
            return json.dumps(face_data, ensure_ascii=False)
        except TypeError:
            return str(face_data)
    if face_data is None:
        return ""
    return str(face_data)


def _read_face_attachment(face_dir: Path, stem: str) -> dict[str, Any]:
    path = face_dir / f"{stem}.json"
    if not path.exists():
        raise FileNotFoundError("面诊记录不存在")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("面诊记录格式无效") from exc

    if not isinstance(payload, dict):
        raise ValueError("面诊记录格式无效")

    face_data = payload.get("faceData")
    prompt_text = _extract_face_prompt(face_data)

    return {
        "recordName": stem,
        "faceData": face_data if face_data is not None else {},
        "facePrompt": prompt_text,
    }


def _list_record_names(records_dir: Path) -> list[str]:
    if not records_dir.exists():
        return []
    names: list[str] = []
    for entry in records_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".json":
            continue
        record_name = _safe_basename_to_record_name(entry.stem)
        if record_name:
            names.append(record_name)
    names.sort(reverse=True)
    return names


def _build_unique_record_name(records_dir: Path) -> str:
    base_name = _format_record_name()
    existing = set(_list_record_names(records_dir))
    if base_name not in existing:
        return base_name
    suffix = 1
    while True:
        suffix_text = _pad2(suffix) if suffix <= 99 else str(suffix)
        candidate = f"{base_name}-{suffix_text}"
        if candidate not in existing:
            return candidate
        suffix += 1


def _read_record_messages(records_dir: Path, record_name: str) -> list[dict[str, str]]:
    candidates = [
        records_dir / f"{_record_name_to_safe_basename(record_name)}.json",
        records_dir / f"{record_name}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if isinstance(messages, list):
            result: list[dict[str, str]] = []
            for item in messages:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip()
                content = str(item.get("content") or "")
                if role in ("user", "assistant") and content.strip():
                    result.append({"role": role, "content": content})
            return result
    raise FileNotFoundError("记录不存在")


def _write_record(records_dir: Path, record_name: str, messages: list[dict[str, str]], owner: str) -> None:
    file_path = records_dir / f"{_record_name_to_safe_basename(record_name)}.json"
    payload = {
        "recordName": record_name,
        "owner": owner,
        "updatedAt": datetime.now().isoformat(),
        "messages": messages,
    }
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(file_path)


def _is_ollama_endpoint(endpoint: str) -> bool:
    return "127.0.0.1:11434" in endpoint or "localhost:11434" in endpoint


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


@router.get("/api/chat/config")
async def get_chat_config() -> JSONResponse:
    raw = _load_chat_config_raw()
    resolved, options = _resolve_option(raw, None)

    payload = {
        "apiEndpoint": resolved.api_endpoint if resolved else "",
        "model": resolved.model if resolved else "",
        "selectedOptionName": resolved.name if resolved else "",
        "stream": resolved.stream if resolved else False,
        "temperature": resolved.temperature,
        "modelOptions": [
            {
                "name": item.name,
                "model": item.model,
                "apiEndpoint": item.api_endpoint,
                "systemPrompt": item.system_prompt,
                "stream": item.stream,
                "temperature": item.temperature,
            }
            for item in options
        ],
        "systemPrompt": (resolved.system_prompt if resolved else _read_text_file(PROMPT_PATH)),
    }
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/chat")
async def chat_records_get(
    request: Request,
    action: str = Query(default="list"),
    name: str = Query(default=""),
) -> JSONResponse:
    records_dir = _get_user_records_dir(request)

    if action == "list":
        return JSONResponse(
            content={"records": _list_record_names(records_dir)},
            headers={"Cache-Control": "no-store"},
        )

    if action == "load":
        record_name = _sanitize_record_name(name)
        if not record_name:
            return JSONResponse(
                status_code=400,
                content={"error": "name 参数无效，格式应为 yy-mm-ddThh:mm"},
            )
        try:
            messages = _read_record_messages(records_dir, record_name)
        except FileNotFoundError:
            return JSONResponse(status_code=404, content={"error": "记录不存在"})
        return JSONResponse(
            content={"recordName": record_name, "messages": messages},
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(status_code=400, content={"error": "不支持的 action 参数"})


@router.get("/api/chat/face")
async def chat_face_records_get(
    request: Request,
    action: str = Query(default="list"),
    name: str = Query(default=""),
) -> JSONResponse:
    face_dir = _get_user_face_dir(request)

    if action == "list":
        return JSONResponse(
            content={"records": _list_face_record_stems(face_dir)},
            headers={"Cache-Control": "no-store"},
        )

    if action == "load":
        record_stem = _sanitize_face_record_stem(name)
        if not record_stem:
            return JSONResponse(
                status_code=400,
                content={"error": "name 参数无效，格式应为 face-yy-mm-ddThh-mm"},
            )
        try:
            attachment = _read_face_attachment(face_dir, record_stem)
        except FileNotFoundError:
            return JSONResponse(status_code=404, content={"error": "面诊记录不存在"})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

        return JSONResponse(
            content=attachment,
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(status_code=400, content={"error": "不支持的 action 参数"})


@router.put("/api/chat")
async def chat_records_put(request: Request, body: SaveBody) -> JSONResponse:
    messages = _normalize_persist_messages(body.messages)
    if not messages:
        return JSONResponse(status_code=400, content={"error": "messages 不能为空"})

    provided_record_name = (body.recordName or "").strip()
    sanitized_record_name = _sanitize_record_name(provided_record_name)
    if provided_record_name and not sanitized_record_name:
        return JSONResponse(
            status_code=400,
            content={"error": "recordName 参数无效，格式应为 yy-mm-ddThh:mm"},
        )

    records_dir = _get_user_records_dir(request)
    record_name = sanitized_record_name or _build_unique_record_name(records_dir)
    owner = _safe_username(_get_session_username(request))

    with _STORE_LOCK:
        _write_record(records_dir, record_name, messages, owner)

    return JSONResponse(
        content={
            "recordName": record_name,
            "records": _list_record_names(records_dir),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/chat")
async def chat_proxy(body: ChatBody) -> Response:
    if not body.messages:
        return JSONResponse(status_code=400, content={"error": "messages 不能为空"})

    raw = _load_chat_config_raw()
    resolved, _ = _resolve_option(raw, body.selectedOptionName)

    if resolved is None or not resolved.api_endpoint or not resolved.model:
        return JSONResponse(status_code=500, content={"error": "RD/chat/api.json 配置不完整"})

    env_map = _load_env_map()
    api_key = _resolve_api_key(resolved.api_key_env, resolved.api_key, env_map)
    if resolved.api_key_env and not api_key:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"环境变量 {resolved.api_key_env} 未设置，请在 .env 中配置后重启服务"
            },
        )

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload_messages = _build_upstream_messages(body.messages, resolved.system_prompt)
    requested_stream = body.stream if body.stream is not None else resolved.stream
    requested_temperature = (
        body.temperature
        if body.temperature is not None
        else resolved.temperature
    )

    if requested_temperature is not None:
        requested_temperature = max(0.0, min(2.0, float(requested_temperature)))

    def send_upstream(target_model: str) -> tuple[int, str, str]:
        return _http_json_request(
            url=resolved.api_endpoint,
            method="POST",
            payload=_build_upstream_payload(
                target_model=target_model,
                payload_messages=payload_messages,
                stream=requested_stream,
                temperature=requested_temperature,
            ),
            headers=headers,
        )

    def open_upstream_stream(
        target_model: str,
    ) -> tuple[Any | None, int, str, str]:
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
            response = url_request.urlopen(req, timeout=120)
            return response, int(response.status), str(response.headers.get("Content-Type") or ""), ""
        except url_error.HTTPError as exc:
            content_type = str(exc.headers.get("Content-Type") or "") if exc.headers else ""
            body_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            return None, int(exc.code), content_type, body_text
        except url_error.URLError as exc:
            raise HTTPException(status_code=502, detail=f"上游接口不可达：{exc.reason}") from exc

    if requested_stream:
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

        def plain_text_stream():
            try:
                buffer = ""
                while True:
                    chunk = stream_response.read(1024)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="ignore")
                    output, buffer = _consume_stream_buffer(buffer, final=False)
                    if output:
                        yield output

                tail, _ = _consume_stream_buffer(buffer, final=True)
                if tail:
                    yield tail
            finally:
                try:
                    stream_response.close()
                except Exception:
                    pass

        return StreamingResponse(
            plain_text_stream(),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-store",
                "X-Resolved-Model": active_model,
                "X-Stream-Enabled": "true",
            },
        )

    active_model = resolved.model
    status_code, content_type, upstream_text = send_upstream(active_model)

    if status_code < 200 or status_code >= 300:
        missing_model = _extract_model_not_found(upstream_text)
        if status_code == 404 and missing_model and _is_ollama_endpoint(resolved.api_endpoint):
            retry_model = _resolve_ollama_model_name(resolved.api_endpoint, missing_model)
            if retry_model and retry_model != active_model:
                active_model = retry_model
                status_code, content_type, upstream_text = send_upstream(active_model)

    if status_code < 200 or status_code >= 300:
        media_type = "application/json; charset=utf-8" if "application/json" in content_type else "text/plain; charset=utf-8"
        return Response(content=upstream_text or "上游接口请求失败", status_code=status_code, media_type=media_type)

    if "application/json" in content_type:
        try:
            parsed = json.loads(upstream_text)
            return JSONResponse(
                content=parsed,
                headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model},
            )
        except json.JSONDecodeError:
            return Response(
                content=upstream_text,
                status_code=200,
                media_type="text/plain; charset=utf-8",
                headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model},
            )

    return Response(
        content=upstream_text,
        status_code=200,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model},
    )