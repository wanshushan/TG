from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "rd.sqlite3"

_DB_LOCK = Lock()
_DB_READY = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    return connection


def _safe_json_loads(text: str, default: Any) -> Any:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return default
    return value


def _safe_read_json(path: Path, default: Any) -> Any:
    if not path.exists() or not path.is_file():
        return default
    try:
        return _safe_json_loads(path.read_text(encoding="utf-8"), default)
    except OSError:
        return default


def _record_name_from_safe_name(name: str) -> str:
    # Legacy files use '-' in place of ':' after the 'T'.
    if "T" not in name:
        return name
    prefix, suffix = name.split("T", 1)
    if ":" in suffix:
        return name
    parts = suffix.split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        remain = "-".join(parts[2:])
        rebuilt = f"{parts[0]}:{parts[1]}"
        if remain:
            rebuilt = f"{rebuilt}-{remain}"
        return f"{prefix}T{rebuilt}"
    return name


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            bio TEXT NOT NULL DEFAULT '',
            avatar_path TEXT NOT NULL DEFAULT '',
            links_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_model_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            scope TEXT NOT NULL,
            name TEXT NOT NULL,
            model TEXT NOT NULL,
            api_endpoint TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            api_key_env TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            stream INTEGER NOT NULL DEFAULT 1,
            temperature REAL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
            UNIQUE(username, scope, name)
        );

        CREATE TABLE IF NOT EXISTS conversation_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            scope TEXT NOT NULL,
            record_name TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            extra_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
            UNIQUE(username, scope, record_name)
        );

        CREATE TABLE IF NOT EXISTS diagnosis_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            scope TEXT NOT NULL,
            record_name TEXT NOT NULL,
            image_path TEXT NOT NULL DEFAULT '',
            result_text TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            score INTEGER,
            score_source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
            UNIQUE(username, scope, record_name)
        );

        CREATE TABLE IF NOT EXISTS diagnosis_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            scope TEXT NOT NULL,
            record_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            score_source TEXT NOT NULL DEFAULT '',
            score_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
            UNIQUE(username, scope, record_name)
        );

        CREATE INDEX IF NOT EXISTS idx_conv_user_scope_updated
        ON conversation_records(username, scope, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_diag_user_scope_updated
        ON diagnosis_records(username, scope, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_score_user_scope_time
        ON diagnosis_scores(username, scope, score_time ASC);
        """
    )


def _upsert_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    now = _now_iso()
    connection.execute(
        """
        INSERT INTO metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, now),
    )


def _get_meta(connection: sqlite3.Connection, key: str) -> str:
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]).strip() if row else ""


def _ensure_user_exists(connection: sqlite3.Connection, username: str) -> None:
    now = _now_iso()
    connection.execute(
        """
        INSERT INTO users (
            username, password_salt, password_hash, bio, avatar_path,
            links_json, created_at, updated_at
        )
        VALUES (?, '', '', ?, '', '[]', ?, ?)
        ON CONFLICT(username) DO NOTHING
        """,
        (username, f"你好，{username}！欢迎使用灵·诊。", now, now),
    )


def _migrate_users(connection: sqlite3.Connection) -> None:
    users_path = DATA_DIR / "users.json"
    payload = _safe_read_json(users_path, {})
    if not isinstance(payload, dict):
        return

    now = _now_iso()
    for username, raw in payload.items():
        if not isinstance(username, str) or not isinstance(raw, dict):
            continue
        normalized_username = username.strip()
        if not normalized_username:
            continue

        links_value = raw.get("links") if isinstance(raw.get("links"), list) else []
        links_json = json.dumps(links_value, ensure_ascii=False)

        connection.execute(
            """
            INSERT INTO users (
                username, password_salt, password_hash, bio, avatar_path,
                links_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_salt = CASE
                    WHEN users.password_salt = '' THEN excluded.password_salt
                    ELSE users.password_salt
                END,
                password_hash = CASE
                    WHEN users.password_hash = '' THEN excluded.password_hash
                    ELSE users.password_hash
                END,
                bio = CASE
                    WHEN users.bio = '' THEN excluded.bio
                    ELSE users.bio
                END,
                avatar_path = CASE
                    WHEN users.avatar_path = '' THEN excluded.avatar_path
                    ELSE users.avatar_path
                END,
                links_json = CASE
                    WHEN users.links_json = '[]' THEN excluded.links_json
                    ELSE users.links_json
                END,
                updated_at = excluded.updated_at
            """,
            (
                normalized_username,
                str(raw.get("passwordSalt") or "").strip(),
                str(raw.get("passwordHash") or "").strip(),
                str(raw.get("bio") or "").strip(),
                str(raw.get("avatar") or "").strip(),
                links_json,
                now,
                now,
            ),
        )


def _normalize_chat_messages(raw_messages: Any) -> list[dict[str, str]]:
    if not isinstance(raw_messages, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "")
        if role in {"user", "assistant"} and content.strip():
            normalized.append({"role": role, "content": content})
    return normalized


def _migrate_chat_records(connection: sqlite3.Connection) -> None:
    chat_root = DATA_DIR / "chat"
    if not chat_root.exists() or not chat_root.is_dir():
        return

    for user_dir in chat_root.iterdir():
        if not user_dir.is_dir():
            continue
        username = user_dir.name.strip()
        if not username:
            continue

        _ensure_user_exists(connection, username)

        for path in user_dir.glob("*.json"):
            payload = _safe_read_json(path, {})
            if not isinstance(payload, dict):
                continue
            record_name = str(payload.get("recordName") or "").strip()
            if not record_name:
                record_name = _record_name_from_safe_name(path.stem)
            messages = _normalize_chat_messages(payload.get("messages"))
            if not messages:
                continue

            updated_at = str(payload.get("updatedAt") or "").strip() or _now_iso()
            now = _now_iso()
            connection.execute(
                """
                INSERT INTO conversation_records (
                    username, scope, record_name, messages_json, extra_json, created_at, updated_at
                )
                VALUES (?, 'chat', ?, ?, '{}', ?, ?)
                ON CONFLICT(username, scope, record_name)
                DO UPDATE SET
                    messages_json = excluded.messages_json,
                    updated_at = excluded.updated_at
                """,
                (
                    username,
                    record_name,
                    json.dumps(messages, ensure_ascii=False),
                    now,
                    updated_at,
                ),
            )


def _migrate_mental_records(connection: sqlite3.Connection) -> None:
    mental_root = DATA_DIR / "mental"
    if not mental_root.exists() or not mental_root.is_dir():
        return

    for user_dir in mental_root.iterdir():
        if not user_dir.is_dir():
            continue
        username = user_dir.name.strip()
        if not username:
            continue

        _ensure_user_exists(connection, username)

        for record_dir in user_dir.iterdir():
            if not record_dir.is_dir() or not record_dir.name.startswith("mental-"):
                continue

            record_name = record_dir.name.strip()
            record_file = record_dir / f"{record_name}.json"
            payload = _safe_read_json(record_file, {})
            if not isinstance(payload, dict):
                continue

            messages = _normalize_chat_messages(payload.get("messages"))
            updated_at = str(payload.get("updatedAt") or "").strip() or _now_iso()
            now = _now_iso()

            connection.execute(
                """
                INSERT INTO conversation_records (
                    username, scope, record_name, messages_json, extra_json, created_at, updated_at
                )
                VALUES (?, 'mental', ?, ?, '{}', ?, ?)
                ON CONFLICT(username, scope, record_name)
                DO UPDATE SET
                    messages_json = excluded.messages_json,
                    updated_at = excluded.updated_at
                """,
                (
                    username,
                    record_name,
                    json.dumps(messages, ensure_ascii=False),
                    now,
                    updated_at,
                ),
            )

            result_payload = _safe_read_json(record_dir / "result.json", {})
            if isinstance(result_payload, dict):
                sas_value = result_payload.get("sasStandardScore")
                sds_value = result_payload.get("sdsStandardScore")
                if isinstance(sas_value, (int, float)):
                    upsert_score(
                        username=username,
                        scope="mental-sas",
                        record_name=record_name,
                        score=int(round(float(sas_value))),
                        score_source="legacy",
                        score_time=updated_at,
                        connection=connection,
                    )
                if isinstance(sds_value, (int, float)):
                    upsert_score(
                        username=username,
                        scope="mental-sds",
                        record_name=record_name,
                        score=int(round(float(sds_value))),
                        score_source="legacy",
                        score_time=updated_at,
                        connection=connection,
                    )

        for score_path, score_scope in ((user_dir / "sas.json", "mental-sas"), (user_dir / "sds.json", "mental-sds"), (user_dir / "SAS.json", "mental-sas"), (user_dir / "SDS.json", "mental-sds")):
            score_payload = _safe_read_json(score_path, {})
            if not isinstance(score_payload, dict):
                continue
            for record_name, score_value in score_payload.items():
                if not isinstance(record_name, str):
                    continue
                try:
                    numeric_score = int(round(float(score_value)))
                except (TypeError, ValueError):
                    continue
                upsert_score(
                    username=username,
                    scope=score_scope,
                    record_name=record_name.strip(),
                    score=numeric_score,
                    score_source="legacy",
                    score_time=_now_iso(),
                    connection=connection,
                )


def _migrate_face_and_tg_records(connection: sqlite3.Connection, scope: str) -> None:
    root = DATA_DIR / scope
    if not root.exists() or not root.is_dir():
        return

    score_scope = "face" if scope == "face" else "tg"
    score_field = "qixueScore" if scope == "face" else "tizhiScore"

    for user_dir in root.iterdir():
        if not user_dir.is_dir():
            continue
        username = user_dir.name.strip()
        if not username:
            continue

        _ensure_user_exists(connection, username)

        for record_dir in user_dir.iterdir():
            if not record_dir.is_dir() or not record_dir.name.startswith(f"{scope}-"):
                continue

            record_name = record_dir.name.strip()
            record_file = record_dir / f"{record_name}.json"
            payload = _safe_read_json(record_file, {})
            if not isinstance(payload, dict):
                continue

            updated_at = str(payload.get("updatedAt") or "").strip() or _now_iso()
            result_text = ""
            nested_payload = payload.get(f"{scope}Data")
            if isinstance(nested_payload, dict):
                result_text = str(nested_payload.get("rawText") or "").strip()
            if not result_text:
                result_text = str(payload.get("outputText") or "").strip()

            score_value = payload.get(score_field)
            numeric_score: int | None = None
            if isinstance(score_value, (int, float)):
                numeric_score = int(round(float(score_value)))

            connection.execute(
                """
                INSERT INTO diagnosis_records (
                    username, scope, record_name, image_path, result_text,
                    payload_json, score, score_source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username, scope, record_name)
                DO UPDATE SET
                    image_path = excluded.image_path,
                    result_text = excluded.result_text,
                    payload_json = excluded.payload_json,
                    score = excluded.score,
                    score_source = excluded.score_source,
                    updated_at = excluded.updated_at
                """,
                (
                    username,
                    score_scope,
                    record_name,
                    str(payload.get("imagePath") or "").strip(),
                    result_text,
                    json.dumps(payload, ensure_ascii=False),
                    numeric_score,
                    str(payload.get(f"{score_field}Source") or payload.get("scoreSource") or "legacy").strip(),
                    updated_at,
                    updated_at,
                ),
            )

            if numeric_score is not None:
                upsert_score(
                    username=username,
                    scope=score_scope,
                    record_name=record_name,
                    score=numeric_score,
                    score_source="legacy",
                    score_time=updated_at,
                    connection=connection,
                )

        score_payload = _safe_read_json(user_dir / "socre.json", {})
        if isinstance(score_payload, dict) and isinstance(score_payload.get("records"), list):
            for item in score_payload.get("records", []):
                if not isinstance(item, dict):
                    continue
                record_name = str(item.get("recordName") or "").strip()
                if not record_name:
                    continue
                try:
                    numeric_score = int(round(float(item.get("score"))))
                except (TypeError, ValueError):
                    continue
                upsert_score(
                    username=username,
                    scope=score_scope,
                    record_name=record_name,
                    score=numeric_score,
                    score_source=str(item.get("scoreSource") or "legacy").strip(),
                    score_time=str(item.get("time") or "").strip() or _now_iso(),
                    connection=connection,
                )


def _migrate_legacy_data(connection: sqlite3.Connection) -> None:
    if _get_meta(connection, "legacy_import_done") == "1":
        return

    _migrate_users(connection)
    _migrate_chat_records(connection)
    _migrate_mental_records(connection)
    _migrate_face_and_tg_records(connection, scope="face")
    _migrate_face_and_tg_records(connection, scope="tg")

    _upsert_meta(connection, "legacy_import_done", "1")


def initialize_database() -> None:
    global _DB_READY
    if _DB_READY:
        return

    with _DB_LOCK:
        if _DB_READY:
            return

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _connect() as connection:
            _create_schema(connection)
            _migrate_legacy_data(connection)
            connection.commit()

        _DB_READY = True


def get_user(username: str) -> dict[str, Any] | None:
    normalized = (username or "").strip()
    if not normalized:
        return None

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT username, password_salt, password_hash, bio, avatar_path, links_json
            FROM users
            WHERE username = ?
            """,
            (normalized,),
        ).fetchone()

    if not row:
        return None

    links = _safe_json_loads(str(row["links_json"] or "[]"), [])
    if not isinstance(links, list):
        links = []

    return {
        "username": str(row["username"]),
        "passwordSalt": str(row["password_salt"] or ""),
        "passwordHash": str(row["password_hash"] or ""),
        "bio": str(row["bio"] or ""),
        "avatar": str(row["avatar_path"] or ""),
        "links": links,
    }


def create_user(
    username: str,
    password_salt: str,
    password_hash: str,
    bio: str,
    avatar: str,
    links: list[dict[str, Any]] | None = None,
) -> None:
    normalized = (username or "").strip()
    if not normalized:
        raise ValueError("用户名不能为空")

    initialize_database()
    now = _now_iso()
    links_json = json.dumps(links or [], ensure_ascii=False)

    with _DB_LOCK, _connect() as connection:
        try:
            connection.execute(
                """
                INSERT INTO users (
                    username, password_salt, password_hash, bio, avatar_path,
                    links_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    password_salt,
                    password_hash,
                    bio,
                    avatar,
                    links_json,
                    now,
                    now,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc


def update_user_avatar(username: str, avatar_path: str) -> None:
    normalized = (username or "").strip()
    if not normalized:
        return

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE users
            SET avatar_path = ?, updated_at = ?
            WHERE username = ?
            """,
            (avatar_path.strip(), _now_iso(), normalized),
        )
        connection.commit()


def list_user_model_options(username: str, scope: str) -> list[dict[str, Any]]:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    if not normalized_username or not normalized_scope:
        return []

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT name, model, api_endpoint, api_key, api_key_env,
                   system_prompt, stream, temperature
            FROM user_model_options
            WHERE username = ? AND scope = ? AND is_enabled = 1
            ORDER BY id ASC
            """,
            (normalized_username, normalized_scope),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "name": str(row["name"] or ""),
                "model": str(row["model"] or ""),
                "apiEndpoint": str(row["api_endpoint"] or ""),
                "apiKey": str(row["api_key"] or ""),
                "apiKeyEnv": str(row["api_key_env"] or ""),
                "systemPrompt": str(row["system_prompt"] or ""),
                "stream": bool(int(row["stream"] or 0)),
                "temperature": row["temperature"],
            }
        )
    return result


def upsert_user_model_option(
    username: str,
    scope: str,
    name: str,
    model: str,
    api_endpoint: str,
    api_key: str,
    api_key_env: str = "",
    system_prompt: str = "",
    stream: bool = True,
    temperature: float | None = None,
) -> None:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    normalized_name = (name or "").strip()
    normalized_model = (model or "").strip()
    normalized_endpoint = (api_endpoint or "").strip()

    if not normalized_username or not normalized_scope or not normalized_name or not normalized_model or not normalized_endpoint:
        raise ValueError("模型配置不完整")

    initialize_database()
    now = _now_iso()
    with _DB_LOCK, _connect() as connection:
        _ensure_user_exists(connection, normalized_username)
        connection.execute(
            """
            INSERT INTO user_model_options (
                username, scope, name, model, api_endpoint, api_key,
                api_key_env, system_prompt, stream, temperature,
                is_enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(username, scope, name)
            DO UPDATE SET
                model = excluded.model,
                api_endpoint = excluded.api_endpoint,
                api_key = excluded.api_key,
                api_key_env = excluded.api_key_env,
                system_prompt = excluded.system_prompt,
                stream = excluded.stream,
                temperature = excluded.temperature,
                is_enabled = 1,
                updated_at = excluded.updated_at
            """,
            (
                normalized_username,
                normalized_scope,
                normalized_name,
                normalized_model,
                normalized_endpoint,
                (api_key or "").strip(),
                (api_key_env or "").strip(),
                (system_prompt or "").strip(),
                1 if stream else 0,
                temperature,
                now,
                now,
            ),
        )
        connection.commit()


def list_conversation_records(username: str, scope: str) -> list[str]:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    if not normalized_username or not normalized_scope:
        return []

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT record_name
            FROM conversation_records
            WHERE username = ? AND scope = ?
            ORDER BY record_name DESC
            """,
            (normalized_username, normalized_scope),
        ).fetchall()

    return [str(row["record_name"]) for row in rows]


def get_conversation_messages(username: str, scope: str, record_name: str) -> list[dict[str, str]]:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    normalized_record = (record_name or "").strip()
    if not normalized_username or not normalized_scope or not normalized_record:
        raise FileNotFoundError("记录不存在")

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT messages_json
            FROM conversation_records
            WHERE username = ? AND scope = ? AND record_name = ?
            """,
            (normalized_username, normalized_scope, normalized_record),
        ).fetchone()

    if not row:
        raise FileNotFoundError("记录不存在")

    messages = _safe_json_loads(str(row["messages_json"] or "[]"), [])
    return _normalize_chat_messages(messages)


def save_conversation_record(
    username: str,
    scope: str,
    record_name: str,
    messages: list[dict[str, str]],
    extra: dict[str, Any] | None = None,
) -> None:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    normalized_record = (record_name or "").strip()
    if not normalized_username or not normalized_scope or not normalized_record:
        raise ValueError("记录信息不完整")

    normalized_messages = _normalize_chat_messages(messages)
    if not normalized_messages:
        raise ValueError("messages 不能为空")

    initialize_database()
    now = _now_iso()
    with _DB_LOCK, _connect() as connection:
        _ensure_user_exists(connection, normalized_username)
        connection.execute(
            """
            INSERT INTO conversation_records (
                username, scope, record_name, messages_json,
                extra_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, scope, record_name)
            DO UPDATE SET
                messages_json = excluded.messages_json,
                extra_json = excluded.extra_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized_username,
                normalized_scope,
                normalized_record,
                json.dumps(normalized_messages, ensure_ascii=False),
                json.dumps(extra or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        connection.commit()


def get_next_record_name(username: str, scope: str, base_name: str) -> str:
    normalized_base = (base_name or "").strip()
    if not normalized_base:
        raise ValueError("base_name 不能为空")

    exists = set(list_conversation_records(username, scope))
    if normalized_base not in exists:
        return normalized_base

    suffix = 1
    while True:
        suffix_text = f"{suffix:02d}" if suffix <= 99 else str(suffix)
        candidate = f"{normalized_base}-{suffix_text}"
        if candidate not in exists:
            return candidate
        suffix += 1


def save_diagnosis_record(
    username: str,
    scope: str,
    record_name: str,
    image_path: str,
    result_text: str,
    payload: dict[str, Any],
    score: int | None = None,
    score_source: str = "",
) -> None:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    normalized_record = (record_name or "").strip()
    if not normalized_username or not normalized_scope or not normalized_record:
        raise ValueError("诊断记录信息不完整")

    initialize_database()
    now = _now_iso()
    with _DB_LOCK, _connect() as connection:
        _ensure_user_exists(connection, normalized_username)
        connection.execute(
            """
            INSERT INTO diagnosis_records (
                username, scope, record_name, image_path, result_text,
                payload_json, score, score_source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, scope, record_name)
            DO UPDATE SET
                image_path = excluded.image_path,
                result_text = excluded.result_text,
                payload_json = excluded.payload_json,
                score = excluded.score,
                score_source = excluded.score_source,
                updated_at = excluded.updated_at
            """,
            (
                normalized_username,
                normalized_scope,
                normalized_record,
                (image_path or "").strip(),
                (result_text or "").strip(),
                json.dumps(payload or {}, ensure_ascii=False),
                score,
                (score_source or "").strip(),
                now,
                now,
            ),
        )
        connection.commit()


def list_diagnosis_record_names(username: str, scope: str) -> list[str]:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    if not normalized_username or not normalized_scope:
        return []

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT record_name
            FROM diagnosis_records
            WHERE username = ? AND scope = ?
            ORDER BY record_name DESC
            """,
            (normalized_username, normalized_scope),
        ).fetchall()

    return [str(row["record_name"]) for row in rows]


def get_diagnosis_record(username: str, scope: str, record_name: str) -> dict[str, Any] | None:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    normalized_record = (record_name or "").strip()
    if not normalized_username or not normalized_scope or not normalized_record:
        return None

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT image_path, result_text, payload_json, score, score_source, updated_at
            FROM diagnosis_records
            WHERE username = ? AND scope = ? AND record_name = ?
            """,
            (normalized_username, normalized_scope, normalized_record),
        ).fetchone()

    if not row:
        return None

    payload = _safe_json_loads(str(row["payload_json"] or "{}"), {})
    if not isinstance(payload, dict):
        payload = {}

    return {
        "recordName": normalized_record,
        "imagePath": str(row["image_path"] or ""),
        "resultText": str(row["result_text"] or ""),
        "payload": payload,
        "score": row["score"],
        "scoreSource": str(row["score_source"] or ""),
        "updatedAt": str(row["updated_at"] or ""),
    }


def upsert_score(
    username: str,
    scope: str,
    record_name: str,
    score: int,
    score_source: str,
    score_time: str | None = None,
    connection: sqlite3.Connection | None = None,
) -> None:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    normalized_record = (record_name or "").strip()
    if not normalized_username or not normalized_scope or not normalized_record:
        return

    time_value = (score_time or "").strip() or _now_iso()
    now = _now_iso()

    def _execute(conn: sqlite3.Connection) -> None:
        _ensure_user_exists(conn, normalized_username)
        conn.execute(
            """
            INSERT INTO diagnosis_scores (
                username, scope, record_name, score, score_source,
                score_time, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, scope, record_name)
            DO UPDATE SET
                score = excluded.score,
                score_source = excluded.score_source,
                score_time = excluded.score_time,
                updated_at = excluded.updated_at
            """,
            (
                normalized_username,
                normalized_scope,
                normalized_record,
                int(score),
                (score_source or "").strip(),
                time_value,
                now,
                now,
            ),
        )

    if connection is not None:
        _execute(connection)
        return

    initialize_database()
    with _DB_LOCK, _connect() as conn:
        _execute(conn)
        conn.commit()


def list_scores(username: str, scope: str) -> list[dict[str, Any]]:
    normalized_username = (username or "").strip()
    normalized_scope = (scope or "").strip().lower()
    if not normalized_username or not normalized_scope:
        return []

    initialize_database()
    with _DB_LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT record_name, score, score_source, score_time
            FROM diagnosis_scores
            WHERE username = ? AND scope = ?
            ORDER BY score_time ASC, record_name ASC
            """,
            (normalized_username, normalized_scope),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "recordName": str(row["record_name"]),
                "score": int(row["score"]),
                "scoreSource": str(row["score_source"] or ""),
                "time": str(row["score_time"] or ""),
            }
        )
    return result
