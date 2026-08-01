"""Encrypted integration configuration storage.

This store keeps public integration metadata and encrypted provider secrets in a
small SQLite database under backend/data. Secret values never need to be written
to .env or returned to the frontend.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from config.settings import get_settings


SECRET_FIELDS = {
    "app_secret",
    "access_token",
    "long_lived_access_token",
    "page_access_token",
    "client_secret",
    "refresh_token",
    "webhook_verify_token",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_dir() -> Path:
    base = Path(get_settings().hunts_dir).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def _db_path() -> Path:
    path = _data_dir() / "secure_integrations.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _key_path() -> Path:
    return _data_dir() / "secure_integrations.key"


def _ensure_private_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_fernet() -> Fernet:
    path = _key_path()
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
        _ensure_private_file(path)
    return Fernet(path.read_bytes().strip())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_configs (
            provider TEXT PRIMARY KEY,
            public_json TEXT NOT NULL,
            secret_encrypted TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'unconfigured',
            scopes TEXT NOT NULL DEFAULT '',
            last_test_at TEXT NOT NULL DEFAULT '',
            last_test_status TEXT NOT NULL DEFAULT '',
            last_test_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS social_profile_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            profile_url TEXT NOT NULL DEFAULT '',
            handle TEXT NOT NULL DEFAULT '',
            public_data_json TEXT NOT NULL,
            raw_response_encrypted TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def encrypt_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return _load_fernet().encrypt(raw).decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    if not token:
        return {}
    try:
        raw = _load_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"


def _split_config(config: dict[str, Any], existing_secret: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    public: dict[str, Any] = {}
    secret = dict(existing_secret or {})
    for key, value in (config or {}).items():
        if key in SECRET_FIELDS:
            text = str(value or "").strip()
            if text and "****" not in text:
                secret[key] = text
            continue
        public[key] = value
    return public, secret


def get_integration(provider: str, *, include_secrets: bool = False) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM integration_configs WHERE provider = ?", (provider,)).fetchone()
    if row is None:
        return {
            "provider": provider,
            "enabled": False,
            "status": "unconfigured",
            "config": {},
            "secret_status": {},
            "scopes": "",
            "last_test_at": "",
            "last_test_status": "",
            "last_test_message": "",
        }

    public = json.loads(row["public_json"] or "{}")
    secret = decrypt_json(row["secret_encrypted"])
    config = dict(public)
    if include_secrets:
        config.update(secret)
    else:
        config.update({key: _mask_secret(value) for key, value in secret.items()})
    return {
        "provider": provider,
        "enabled": bool(row["enabled"]),
        "status": row["status"],
        "config": config,
        "secret_status": {key: bool(value) for key, value in secret.items()},
        "scopes": row["scopes"],
        "last_test_at": row["last_test_at"],
        "last_test_status": row["last_test_status"],
        "last_test_message": row["last_test_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_integrations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT provider FROM integration_configs ORDER BY provider").fetchall()
    return [get_integration(str(row["provider"])) for row in rows]


def save_integration(provider: str, config: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
    existing = get_integration(provider, include_secrets=True)
    existing_secret = {key: value for key, value in (existing.get("config") or {}).items() if key in SECRET_FIELDS}
    public, secret = _split_config(config, existing_secret)
    now = _now_iso()
    status = "configured" if enabled and secret else "saved" if public or secret else "unconfigured"
    with _connect() as conn:
        current = conn.execute("SELECT created_at FROM integration_configs WHERE provider = ?", (provider,)).fetchone()
        conn.execute(
            """
            INSERT INTO integration_configs (
                provider, public_json, secret_encrypted, enabled, status, scopes,
                last_test_at, last_test_status, last_test_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, '', '', '', ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                public_json = excluded.public_json,
                secret_encrypted = excluded.secret_encrypted,
                enabled = excluded.enabled,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                provider,
                json.dumps(public, ensure_ascii=False, sort_keys=True),
                encrypt_json(secret),
                1 if enabled else 0,
                status,
                "",
                current["created_at"] if current else now,
                now,
            ),
        )
        conn.commit()
    return get_integration(provider)


def update_test_result(provider: str, *, ok: bool, message: str, scopes: str = "") -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE integration_configs
            SET status = ?, scopes = ?, last_test_at = ?, last_test_status = ?, last_test_message = ?, updated_at = ?
            WHERE provider = ?
            """,
            ("connected" if ok else "error", scopes, now, "ok" if ok else "error", message[:500], now, provider),
        )
        conn.commit()


def store_social_profile(provider: str, profile_url: str, handle: str, public_data: dict[str, Any], raw_response: dict[str, Any]) -> None:
    cache_key = base64.urlsafe_b64encode(f"{provider}:{profile_url}:{handle}".encode("utf-8")).decode("ascii")
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO social_profile_cache (cache_key, provider, profile_url, handle, public_data_json, raw_response_encrypted, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                public_data_json = excluded.public_data_json,
                raw_response_encrypted = excluded.raw_response_encrypted,
                fetched_at = excluded.fetched_at
            """,
            (
                cache_key,
                provider,
                profile_url,
                handle,
                json.dumps(public_data, ensure_ascii=False, sort_keys=True),
                encrypt_json(raw_response),
                now,
            ),
        )
        conn.commit()
