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
MENTAL_DIR = Path(__file__).resolve().parent
MENTAL_DATA_DIR = BASE_DIR / "data" / "mental"
CONFIG_PATH = MENTAL_DIR / "api.json"
PROMPT_PATH = MENTAL_DIR / "prompt.md"

_STORE_LOCK = Lock()
MENTAL_RECORD_STEM_PATTERN = re.compile(r"^mental-\d{2}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d+)?$")


@dataclass
class ModelOption:
    name: str
    model: str
    api_endpoint: str
    api_key: str
    api_key_env: str
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
    if value is None or isinstance(value, bool):
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


def _load_mental_config_raw() -> dict[str, Any]:
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
    fallback_stream = _to_bool(raw.get("stream"), default=False)
    fallback_temperature = _to_optional_float(raw.get("temperature"))

    normalized: list[ModelOption] = []
    for option in options:
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
        if not content or role == "system":
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
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta.get("content")
            choice_message = first.get("message")
            if isinstance(choice_message, dict) and isinstance(choice_message.get("content"), str):
                return choice_message.get("content")
            if isinstance(first.get("text"), str):
                return first.get("text")

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


def _safe_username(username: str) -> str:
    normalized = (username or "").strip()
    if not normalized:
        return "guest"
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", normalized)
    return safe.strip("._") or "guest"


def _get_session_username(request: Request) -> str:
    value = request.session.get("username")
    return value.strip() if isinstance(value, str) else ""


def _get_user_mental_dir(request: Request) -> tuple[str, Path]:
    username = _safe_username(_get_session_username(request))
    user_dir = MENTAL_DATA_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return username, user_dir


def _format_record_stem(now: datetime | None = None) -> str:
    target = now or datetime.now()
    return (
        f"mental-{target.year % 100:02d}-{target.month:02d}-{target.day:02d}"
        f"T{target.hour:02d}-{target.minute:02d}"
    )


def _list_record_names(user_dir: Path) -> list[str]:
    if not user_dir.exists():
        return []
    names: list[str] = []
    for entry in user_dir.iterdir():
        if entry.is_dir() and MENTAL_RECORD_STEM_PATTERN.match(entry.name):
            json_path = entry / f"{entry.name}.json"
            if json_path.exists() and json_path.is_file():
                names.append(entry.name)
    names.sort(reverse=True)
    return names


def _build_unique_record_stem(user_dir: Path) -> str:
    base = _format_record_stem()
    existing = set(_list_record_names(user_dir))
    if base not in existing:
        return base
    suffix = 1
    while True:
        candidate = f"{base}-{suffix}"
        if candidate not in existing:
            return candidate
        suffix += 1


def _sanitize_record_name(raw_name: str | None) -> str | None:
    name = (raw_name or "").strip()
    if not name:
        return None
    if not MENTAL_RECORD_STEM_PATTERN.match(name):
        return None
    return name


def _record_json_path(user_dir: Path, record_name: str) -> Path:
    return user_dir / record_name / f"{record_name}.json"


def _read_record_messages(user_dir: Path, record_name: str) -> list[dict[str, str]]:
    path = _record_json_path(user_dir, record_name)
    if not path.exists():
        raise FileNotFoundError("记录不存在")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FileNotFoundError("记录不存在") from exc

    raw_messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(raw_messages, list):
        return []

    result: list[dict[str, str]] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "")
        if role in ("user", "assistant") and content.strip():
            result.append({"role": role, "content": content})
    return result


def _write_record(user_dir: Path, record_name: str, owner: str, messages: list[dict[str, str]]) -> Path:
    record_dir = user_dir / record_name
    record_dir.mkdir(parents=True, exist_ok=True)
    file_path = record_dir / f"{record_name}.json"
    payload = {
        "recordName": record_name,
        "owner": owner,
        "updatedAt": datetime.now().isoformat(),
        "messages": messages,
    }
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(file_path)
    return record_dir


def _extract_score(text: str, field: str) -> int | None:
    pattern = rf"{field}\s*标准分\s*[：:]\s*\[?\s*(\d{{1,3}})\s*\]?\s*(?:分)?"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (ValueError, IndexError):
        return None


def _write_score_file(path: Path, record_name: str, score: int) -> None:
    payload: dict[str, int] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = {
                    str(key): int(value)
                    for key, value in raw.items()
                    if isinstance(key, str) and isinstance(value, (int, float, str)) and str(value).strip().isdigit()
                }
        except (OSError, json.JSONDecodeError, ValueError):
            payload = {}

    payload[record_name] = int(score)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _persist_analysis_outputs(user_dir: Path, record_name: str, messages: list[dict[str, str]]) -> None:
    latest_analysis = ""
    for item in reversed(messages):
        if item.get("role") != "assistant":
            continue
        content = item.get("content", "")
        if "【分析结果】" in content:
            latest_analysis = content
            break

    if not latest_analysis:
        return

    record_dir = user_dir / record_name
    record_dir.mkdir(parents=True, exist_ok=True)
    result_path = record_dir / "result.json"

    analysis_text = latest_analysis.split("【分析结果】", 1)[1].strip()

    sas_score = _extract_score(analysis_text, "SAS")
    sds_score = _extract_score(analysis_text, "SDS")

    result_payload = {
        "recordName": record_name,
        "updatedAt": datetime.now().isoformat(),
        "result": analysis_text,
        "sasStandardScore": sas_score,
        "sdsStandardScore": sds_score,
    }
    temp_result = result_path.with_suffix(".tmp")
    temp_result.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_result.replace(result_path)

    if sas_score is not None:
        _write_score_file(user_dir / "sas.json", record_name, sas_score)
    if sds_score is not None:
        _write_score_file(user_dir / "sds.json", record_name, sds_score)


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


@router.get("/api/mental/config")
async def get_mental_config() -> JSONResponse:
    raw = _load_mental_config_raw()
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
                "stream": item.stream,
                "temperature": item.temperature,
            }
            for item in options
        ],
        "systemPrompt": _read_text_file(PROMPT_PATH),
    }
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


@router.get("/api/mental")
async def mental_records_get(
    request: Request,
    action: str = Query(default="list"),
    name: str = Query(default=""),
) -> JSONResponse:
    _, user_dir = _get_user_mental_dir(request)

    if action == "list":
        return JSONResponse(content={"records": _list_record_names(user_dir)}, headers={"Cache-Control": "no-store"})

    if action == "load":
        record_name = _sanitize_record_name(name)
        if not record_name:
            return JSONResponse(status_code=400, content={"error": "name 参数无效，格式应为 mental-yy-mm-ddThh-mm"})
        try:
            messages = _read_record_messages(user_dir, record_name)
        except FileNotFoundError:
            return JSONResponse(status_code=404, content={"error": "记录不存在"})
        return JSONResponse(content={"recordName": record_name, "messages": messages}, headers={"Cache-Control": "no-store"})

    return JSONResponse(status_code=400, content={"error": "不支持的 action 参数"})


@router.get("/api/chat/mental")
async def mental_records_get_alias(
    request: Request,
    action: str = Query(default="list"),
    name: str = Query(default=""),
) -> JSONResponse:
    return await mental_records_get(request=request, action=action, name=name)


@router.put("/api/mental")
async def mental_records_put(request: Request, body: SaveBody) -> JSONResponse:
    messages = _normalize_persist_messages(body.messages)
    if not messages:
        return JSONResponse(status_code=400, content={"error": "messages 不能为空"})

    provided_record_name = (body.recordName or "").strip()
    sanitized_record_name = _sanitize_record_name(provided_record_name)
    if provided_record_name and not sanitized_record_name:
        return JSONResponse(status_code=400, content={"error": "recordName 参数无效，格式应为 mental-yy-mm-ddThh-mm"})

    owner, user_dir = _get_user_mental_dir(request)
    record_name = sanitized_record_name or _build_unique_record_stem(user_dir)

    with _STORE_LOCK:
        _write_record(user_dir=user_dir, record_name=record_name, owner=owner, messages=messages)
        _persist_analysis_outputs(user_dir=user_dir, record_name=record_name, messages=messages)

    return JSONResponse(
        content={"recordName": record_name, "records": _list_record_names(user_dir)},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/mental")
async def mental_proxy(body: ChatBody) -> Response:
    if not body.messages:
        return JSONResponse(status_code=400, content={"error": "messages 不能为空"})

    raw = _load_mental_config_raw()
    resolved, _ = _resolve_option(raw, body.selectedOptionName)

    if resolved is None or not resolved.api_endpoint or not resolved.model:
        return JSONResponse(status_code=500, content={"error": "RD/docter_mental/api.json 配置不完整"})

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

    payload_messages = _build_upstream_messages(body.messages, _read_text_file(PROMPT_PATH))
    requested_stream = body.stream if body.stream is not None else resolved.stream
    requested_temperature = body.temperature if body.temperature is not None else resolved.temperature

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
            return Response(content=error_text or "上游接口请求失败", status_code=status_code, media_type="text/plain; charset=utf-8")

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
            headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model, "X-Stream-Enabled": "true"},
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
            return JSONResponse(content=parsed, headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model})
        except json.JSONDecodeError:
            return Response(content=upstream_text, status_code=200, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model})

    return Response(content=upstream_text, status_code=200, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store", "X-Resolved-Model": active_model})


@router.get("/api/user/charts/mental")
async def get_mental_charts(request: Request) -> Response:
    username = _safe_username(_get_session_username(request))
    user_dir = MENTAL_DATA_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)

    sas_data: dict[str, int] = {}
    sds_data: dict[str, int] = {}

    sas_path = user_dir / "sas.json"
    sds_path = user_dir / "sds.json"
    sas_path_legacy = user_dir / "SAS.json"
    sds_path_legacy = user_dir / "SDS.json"

    if sas_path.exists() or sas_path_legacy.exists():
        try:
            source_path = sas_path if sas_path.exists() else sas_path_legacy
            raw = json.loads(source_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                sas_data = {
                    str(k): int(v)
                    for k, v in raw.items()
                    if isinstance(k, str) and isinstance(v, (int, float, str)) and str(v).strip().isdigit()
                }
        except (OSError, json.JSONDecodeError, ValueError):
            sas_data = {}

    if sds_path.exists() or sds_path_legacy.exists():
        try:
            source_path = sds_path if sds_path.exists() else sds_path_legacy
            raw = json.loads(source_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                sds_data = {
                    str(k): int(v)
                    for k, v in raw.items()
                    if isinstance(k, str) and isinstance(v, (int, float, str)) and str(v).strip().isdigit()
                }
        except (OSError, json.JSONDecodeError, ValueError):
            sds_data = {}

    names = sorted(set(sas_data.keys()) | set(sds_data.keys()))
    sas_points: list[dict[str, int]] = []
    sds_points: list[dict[str, int]] = []

    for index, name in enumerate(names, start=1):
        if name in sas_data:
            sas_points.append({"x": index, "y": int(sas_data[name])})
        if name in sds_data:
            sds_points.append({"x": index, "y": int(sds_data[name])})

    return JSONResponse(
        content={
            "chart3": {
                "id": "chart-3",
                "title": "SAS焦虑评分趋势",
                "xAxisName": "评估序号",
                "yAxisName": "标准分",
                "points": sas_points,
            },
            "chart4": {
                "id": "chart-4",
                "title": "SDS抑郁评分趋势",
                "xAxisName": "评估序号",
                "yAxisName": "标准分",
                "points": sds_points,
            },
        },
        headers={"Cache-Control": "no-store"},
    )
