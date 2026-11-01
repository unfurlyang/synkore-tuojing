from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class InputMode(str, Enum):
    playback = "playback"
    realtime = "realtime"


class RewriteMode(str, Enum):
    style = "style"
    filter = "filter"


class Preference(BaseModel):
    version: int = 1
    mode: RewriteMode = RewriteMode.filter
    style_prompt: str = Field(default="简洁、直接、保留原意", max_length=8000)
    filter_strength: Literal["conservative", "standard", "strong"] = "strong"
    teacher_profile_id: str | None = None
    teacher_profile_name: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreferenceUpdate(BaseModel):
    mode: RewriteMode | None = None
    style_prompt: str | None = Field(default=None, max_length=8000)
    filter_strength: Literal["conservative", "standard", "strong"] | None = None
    teacher_profile_id: str | None = None
    teacher_profile_name: str | None = None


class TeacherProfile(BaseModel):
    is_preset: bool = False
    sources: list[dict[str, str]] = Field(default_factory=list)
    evidence_note: str = ''
    subjects: list[str] = Field(default_factory=list)
    profile_id: str
    user_id: str
    name: str = Field(min_length=1, max_length=80)
    source_filename: str
    transcript_excerpt: str
    language_features: list[str] = Field(min_length=1, max_length=8)
    teaching_structure: list[str] = Field(min_length=1, max_length=8)
    thinking_patterns: list[str] = Field(min_length=1, max_length=8)
    rewrite_rules: list[str] = Field(min_length=3, max_length=10)
    avoid_features: list[str] = Field(default_factory=list, max_length=8)
    evidence: list[str] = Field(default_factory=list, max_length=10)
    voice_sample_id: str | None = None
    voice_consent: bool = False
    created_at: datetime


class TeacherListResponse(BaseModel):
    items: list[TeacherProfile]


class TextProcessRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    text: str = Field(min_length=1, max_length=12000)
    mode: InputMode = InputMode.playback
    preference_version: int | None = Field(default=None, ge=1)


class SegmentResult(BaseModel):
    segment_id: int
    original_text: str
    candidate_text: str
    processed_text: str
    audio_url: str | None
    status: Literal["ok", "degraded"]
    preference_version: int
    fact_check_passed: bool
    warnings: list[str]
    timings_ms: dict[str, float]


class ProcessResponse(BaseModel):
    request_id: str
    mode: InputMode
    output_mode: RewriteMode = RewriteMode.filter
    teacher_profile_id: str | None = None
    teacher_profile_name: str | None = None
    segments: list[SegmentResult]
    providers: dict[str, str]
    degraded: bool
    warnings: list[str]
    total_latency_ms: float


class TeacherTextRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    teacher_name: str = Field(min_length=1, max_length=80)
    transcript: str = Field(min_length=20, max_length=50000)


class FactCheckResult(BaseModel):
    accepted: bool
    missing: list[str]
    introduced: list[str]

    @property
    def warnings(self) -> list[str]:
        warnings = []
        if self.missing:
            warnings.append("候选文本遗漏关键标记: " + ", ".join(self.missing))
        if self.introduced:
            warnings.append("候选文本新增关键标记: " + ", ".join(self.introduced))
        return warnings
