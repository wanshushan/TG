from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib import error as url_error
from urllib import request as url_request

BASE_DIR = Path(__file__).resolve().parent.parent
FACE_DIR = Path(__file__).resolve().parent
FACE_SCORE_CONFIG_PATH = FACE_DIR / "api_socre.json"
FACE_SCORE_PROMPT_PATH = FACE_DIR / "prompt_socre.md"
FACE_SCORE_DATA_DIR = BASE_DIR / "data" / "face"
_SCORE_LOCK = Lock()


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


def _load_config() -> dict[str, Any]:
	if not FACE_SCORE_CONFIG_PATH.exists():
		return {}
	try:
		payload = json.loads(FACE_SCORE_CONFIG_PATH.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError):
		return {}
	return payload if isinstance(payload, dict) else {}


def _resolve_config() -> tuple[str, str, str, float | None]:
	raw = _load_config()
	endpoint = _normalize_api_endpoint(str(raw.get("apiEndpoint") or "").strip())
	model = str(raw.get("model") or "").strip()
	api_key = str(raw.get("apiKey") or "").strip()
	api_key_env = str(raw.get("apiKeyEnv") or "").strip()
	temperature_value = raw.get("temperature")
	temperature: float | None = None
	if isinstance(temperature_value, (int, float)):
		temperature = float(temperature_value)
	elif isinstance(temperature_value, str):
		try:
			temperature = float(temperature_value.strip())
		except ValueError:
			temperature = None

	if not endpoint or not model:
		raise RuntimeError("RD/doctor_face/api_socre.json 配置不完整")

	if api_key_env:
		env_map = _load_env_map()
		api_key = (os.getenv(api_key_env) or env_map.get(api_key_env, "") or "").strip() or api_key

	return endpoint, model, api_key, temperature


def _extract_text_from_response(payload: Any) -> str:
	if isinstance(payload, dict):
		message = payload.get("message")
		if isinstance(message, dict):
			content = message.get("content")
			if isinstance(content, str):
				return content

		choices = payload.get("choices")
		if isinstance(choices, list) and choices:
			first = choices[0]
			if isinstance(first, dict):
				msg = first.get("message")
				if isinstance(msg, dict) and isinstance(msg.get("content"), str):
					return msg.get("content", "")
				text = first.get("text")
				if isinstance(text, str):
					return text
	if isinstance(payload, str):
		return payload
	return ""


def _request_score_text(diagnosis_text: str) -> str:
	endpoint, model, api_key, temperature = _resolve_config()
	prompt_text = _read_text_file(FACE_SCORE_PROMPT_PATH)
	if not prompt_text:
		raise RuntimeError("RD/doctor_face/prompt_socre.md 为空或不存在")

	user_text = f"{prompt_text}\n\n诊断结果：\n{diagnosis_text.strip()}"
	payload: dict[str, Any] = {
		"model": model,
		"messages": [{"role": "user", "content": user_text}],
		"stream": False,
	}
	if temperature is not None:
		payload["temperature"] = max(0.0, min(2.0, float(temperature)))

	headers = {"Content-Type": "application/json"}
	if api_key:
		headers["Authorization"] = f"Bearer {api_key}"

	req = url_request.Request(
		url=endpoint,
		method="POST",
		data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
		headers=headers,
	)

	try:
		with url_request.urlopen(req, timeout=120) as response:
			body = response.read().decode("utf-8", errors="replace")
	except url_error.HTTPError as exc:
		detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
		raise RuntimeError(f"评分模型请求失败: HTTP {exc.code} {detail}") from exc
	except url_error.URLError as exc:
		raise RuntimeError(f"评分模型接口不可达: {exc.reason}") from exc

	try:
		parsed = json.loads(body)
	except json.JSONDecodeError:
		return body.strip()
	return _extract_text_from_response(parsed).strip()


def _parse_score_value(score_text: str) -> int:
	match = re.search(r"(?<!\d)(100|[1-9]?\d)(?!\d)", score_text)
	if not match:
		raise RuntimeError(f"无法从评分输出中解析数字: {score_text}")
	value = int(match.group(1))
	return max(0, min(100, value))


def _heuristic_face_score(diagnosis_text: str) -> int:
	text = diagnosis_text
	score = 70

	positive_keywords = ["红润", "光泽", "正常", "均匀", "荣", "湿润", "淡红"]
	negative_keywords = ["苍白", "萎黄", "暗沉", "发黑", "枯", "干燥", "紫", "裂纹", "厚腻"]

	for keyword in positive_keywords:
		if keyword in text:
			score += 6

	for keyword in negative_keywords:
		if keyword in text:
			score -= 8

	return max(0, min(100, score))


def score_face_qixue(diagnosis_text: str) -> tuple[int, str, bool]:
	try:
		score_text = _request_score_text(diagnosis_text)
		score_value = _parse_score_value(score_text)
		from_llm = True
	except Exception:
		score_value = _heuristic_face_score(diagnosis_text)
		from_llm = False
	prefix = "-" if from_llm else ""
	return score_value, f"{prefix}【气血评分】：{score_value}", from_llm


def append_face_socre(
	username: str,
	record_name: str,
	score: int,
	score_source: str = "fallback",
	time_text: str | None = None,
) -> None:
	user_dir = FACE_SCORE_DATA_DIR / username
	user_dir.mkdir(parents=True, exist_ok=True)
	score_path = user_dir / "socre.json"
	current_time = (time_text or datetime.now().isoformat()).strip()

	with _SCORE_LOCK:
		records: list[dict[str, Any]] = []
		if score_path.exists():
			try:
				raw = json.loads(score_path.read_text(encoding="utf-8") or "{}")
				if isinstance(raw, dict) and isinstance(raw.get("records"), list):
					for item in raw["records"]:
						if isinstance(item, dict):
							records.append(dict(item))
			except (OSError, json.JSONDecodeError):
				records = []

		replaced = False
		for item in records:
			if str(item.get("recordName") or "") == record_name:
				item["time"] = current_time
				item["score"] = int(score)
				item["scoreSource"] = score_source
				replaced = True
				break

		if not replaced:
			records.append({
				"time": current_time,
				"recordName": record_name,
				"score": int(score),
				"scoreSource": score_source,
			})

		def sort_key(item: dict[str, Any]) -> tuple[int, str]:
			text = str(item.get("time") or "")
			try:
				return (0, datetime.fromisoformat(text).isoformat())
			except ValueError:
				return (1, text)

		records.sort(key=sort_key)

		payload = {
			"metric": "qixue",
			"records": records,
		}
		temp_path = score_path.with_suffix(".tmp")
		temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
		temp_path.replace(score_path)
