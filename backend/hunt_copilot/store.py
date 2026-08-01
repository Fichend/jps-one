"""JSON-backed session store for Hunt Copilot."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from config.settings import get_settings
from hunt_copilot.schemas import CopilotSession


class HuntCopilotStore:
    _lock = threading.RLock()

    def __init__(self, path: str | None = None) -> None:
        settings = get_settings()
        base = Path(settings.hunts_dir).resolve().parent
        self.path = Path(path) if path else base / "hunt_copilot_sessions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> dict[str, CopilotSession]:
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
            if not isinstance(raw, dict):
                return {}
            sessions: dict[str, CopilotSession] = {}
            for key, value in raw.items():
                try:
                    sessions[str(key)] = CopilotSession.model_validate(value)
                except Exception:
                    continue
            return sessions

    def save(self, session: CopilotSession) -> None:
        with self._lock:
            sessions = self.load_all()
            sessions[session.session_id] = session
            payload = {key: value.model_dump(mode="json") for key, value in sessions.items()}
            temp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)

    def get(self, session_id: str) -> CopilotSession | None:
        return self.load_all().get(session_id)

    def list_recent(self, *, limit: int = 50) -> list[CopilotSession]:
        sessions = list(self.load_all().values())
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions[: max(1, int(limit))]
