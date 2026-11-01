from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import Preference, PreferenceUpdate


class PreferenceNotFound(KeyError):
    pass


class PreferenceStore:
    """Small persistent store with versioned updates and one-step undo."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"users": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("偏好存储无法读取，请先修复或备份数据文件") from exc
        if not isinstance(data.get("users"), dict):
            raise RuntimeError("偏好存储格式无效")
        return data

    def _write(self, data: dict) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def get(self, user_id: str) -> Preference:
        with self._lock:
            record = self._read()["users"].get(user_id)
            if not record:
                return Preference()
            return Preference.model_validate(record["current"])

    def update(self, user_id: str, update: PreferenceUpdate) -> Preference:
        with self._lock:
            data = self._read()
            record = data["users"].get(user_id, {})
            current = Preference.model_validate(record["current"]) if record else Preference()
            changes = update.model_dump(exclude_none=True)
            if not changes:
                return current
            updated = current.model_copy(
                update={**changes, "version": current.version + 1, "updated_at": datetime.now(timezone.utc)}
            )
            data["users"][user_id] = {
                "current": updated.model_dump(mode="json"),
                "previous": current.model_dump(mode="json"),
            }
            self._write(data)
            return updated

    def undo(self, user_id: str) -> Preference:
        with self._lock:
            data = self._read()
            record = data["users"].get(user_id)
            if not record or "previous" not in record:
                raise PreferenceNotFound(user_id)
            current = Preference.model_validate(record["current"])
            previous = Preference.model_validate(record["previous"])
            restored = previous.model_copy(
                update={"version": current.version + 1, "updated_at": datetime.now(timezone.utc)}
            )
            record["current"] = restored.model_dump(mode="json")
            record.pop("previous", None)
            self._write(data)
            return restored
