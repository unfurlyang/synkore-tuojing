from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline import VoicePipeline
from app.preferences import PreferenceStore
from app.providers.base import AudioData
from app.providers.rules import RuleRewriter
from app.schemas import InputMode
from app.teachers import TeacherStore


TRANSCRIPT = "我们先从问题出发，再建立公式。大家注意，这个结论成立有三个条件。接下来用一个生活中的例子解释为什么要先判断方向，最后总结解题步骤。"


class FakeASR:
    name = "fake-asr-test"

    async def transcribe(self, content, filename, content_type):
        return TRANSCRIPT


class FakeTTS:
    name = "fake-tts-test"

    async def synthesize(self, text):
        return AudioData(content=b"RIFF-test", content_type="audio/wav", extension=".wav")


class FakeProfiler:
    name = "fake-profiler-test"

    async def distill(self, transcript, teacher_name):
        assert TRANSCRIPT in transcript
        return {
            "language_features": ["短句讲解，先提出问题"],
            "teaching_structure": ["问题、公式、例子、总结"],
            "thinking_patterns": ["先检查条件，再推理"],
            "rewrite_rules": ["先提出核心问题", "解释公式前先检查条件", "最后总结步骤"],
            "avoid_features": ["不模仿口头重复"],
            "evidence": ["我们先从问题出发"],
        }


def make_pipeline(tmp_path):
    return VoicePipeline(
        FakeASR(),
        RuleRewriter(),
        FakeTTS(),
        PreferenceStore(tmp_path / "preferences.json"),
        tmp_path / "audio",
        TeacherStore(tmp_path / "teachers.json"),
        FakeProfiler(),
    )


def test_teacher_profile_is_persistent_and_selectable(tmp_path):
    pipeline = make_pipeline(tmp_path)
    client = TestClient(create_app(Settings.from_env(), pipeline))
    created = client.post(
        "/v1/teachers/from-text",
        json={"user_id": "user-a", "teacher_name": "物理老师", "transcript": TRANSCRIPT},
    )
    assert created.status_code == 200, created.text
    profile = created.json()
    assert profile["thinking_patterns"] == ["先检查条件，再推理"]

    selected = client.put(f"/v1/preferences/user-a/teacher/{profile['profile_id']}")
    assert selected.status_code == 200, selected.text
    preference = selected.json()
    assert preference["mode"] == "filter"
    assert preference["teacher_profile_name"] == "物理老师"
    assert "先提出核心问题" in preference["style_prompt"]

    listed = client.get("/v1/teachers", params={"user_id": "user-a"})
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 4
    assert sum(p["is_preset"] for p in listed.json()["items"]) == 3
    assert any(p["profile_id"] == profile["profile_id"] for p in listed.json()["items"])

    restored = VoicePipeline(
        FakeASR(), RuleRewriter(), FakeTTS(), PreferenceStore(tmp_path / "preferences.json"), tmp_path / "audio",
        TeacherStore(tmp_path / "teachers.json"), FakeProfiler(),
    )
    assert restored.teacher_profiles.get("user-a", profile["profile_id"]).name == "物理老师"


def test_audio_distillation_uses_chunked_transcripts(tmp_path, monkeypatch):
    pipeline = make_pipeline(tmp_path)
    client = TestClient(create_app(Settings.from_env(), pipeline))

    async def fake_chunks(content, extension, start_seconds, duration_seconds):
        assert extension == ".m4a"
        assert duration_seconds is None
        return [b"chunk-1", b"chunk-2"]

    monkeypatch.setattr("app.main.convert_audio_to_wav_chunks", fake_chunks)
    response = client.post(
        "/v1/teachers/distill",
        data={"user_id": "user-a", "teacher_name": "物理老师", "full_course": "true", "voice_consent": "true"},
        files={"file": ("lesson.m4a", b"audio", "audio/mp4")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["source_filename"] == "lesson.m4a"
    assert response.json()["voice_consent"] is True
    voice_sample_id = response.json()["voice_sample_id"]
    assert voice_sample_id
    assert (pipeline.voice_dir / f"{voice_sample_id}.wav").read_bytes() == b"chunk-1"


def test_cannot_select_another_users_teacher(tmp_path):
    pipeline = make_pipeline(tmp_path)
    client = TestClient(create_app(Settings.from_env(), pipeline))
    profile = client.post(
        "/v1/teachers/from-text",
        json={"user_id": "user-a", "teacher_name": "物理老师", "transcript": TRANSCRIPT},
    ).json()
    response = client.put(f"/v1/preferences/user-b/teacher/{profile['profile_id']}")
    assert response.status_code == 404
