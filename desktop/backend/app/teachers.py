from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import TeacherProfile


class TeacherNotFound(KeyError):
    pass


def teacher_style_prompt(profile: TeacherProfile) -> str:
    def lines(title: str, items: list[str]) -> str:
        return title + "\n" + "\n".join(f"- {item}" for item in items)

    return "\n".join(
        [
            f"目标教师画像：{profile.name}",
            lines("语言特点", profile.language_features[:3]),
            lines("讲课结构", profile.teaching_structure[:2]),
            lines("思维方式", profile.thinking_patterns[:3]),
            lines("必须执行的改写规则", profile.rewrite_rules[:5]),
            lines("不要模仿", profile.avoid_features[:4]),
            "只迁移表达方式、语言组织和推理路径，不搬运画像中的知识内容；音色由独立授权的声音参考控制。",
        ]
    )


class TeacherStore:
    """Persistent, user-scoped teacher lecture profiles."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"profiles": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("教师画像存储无法读取，请先修复或备份数据文件") from exc
        if not isinstance(data.get("profiles"), dict):
            raise RuntimeError("教师画像存储格式无效")
        return data

    def _write(self, data: dict) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def list(self, user_id: str) -> list[TeacherProfile]:
        from app.public_catalog import preset_profiles
        with self._lock:
            records = self._read()["profiles"].values()
            profiles = [TeacherProfile.model_validate(item) for item in records if item.get("user_id") == user_id]
        return preset_profiles(user_id) + sorted(profiles, key=lambda item: item.created_at, reverse=True)

    def get(self, user_id: str, profile_id: str) -> TeacherProfile:
        from app.public_catalog import preset_profiles
        preset = next((p for p in preset_profiles(user_id) if p.profile_id == profile_id), None)
        if preset:
            return preset
        with self._lock:
            record = self._read()["profiles"].get(profile_id)
        if not record or record.get("user_id") != user_id:
            raise TeacherNotFound(profile_id)
        return TeacherProfile.model_validate(record)

    def create(
        self,
        user_id: str,
        name: str,
        source_filename: str,
        transcript: str,
        analysis: dict,
        voice_sample_id: str | None = None,
        voice_consent: bool = False,
    ) -> TeacherProfile:
        profile = TeacherProfile(
            profile_id=uuid.uuid4().hex,
            user_id=user_id,
            name=name,
            source_filename=source_filename,
            transcript_excerpt=transcript[:12000],
            language_features=analysis["language_features"],
            teaching_structure=analysis["teaching_structure"],
            thinking_patterns=analysis["thinking_patterns"],
            rewrite_rules=analysis["rewrite_rules"],
            avoid_features=analysis["avoid_features"],
            evidence=analysis["evidence"],
            voice_sample_id=voice_sample_id,
            voice_consent=voice_consent and bool(voice_sample_id),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            data = self._read()
            data["profiles"][profile.profile_id] = profile.model_dump(mode="json")
            self._write(data)
        return profile
