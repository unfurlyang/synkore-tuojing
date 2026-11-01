import asyncio

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline import VoicePipeline, realtime_filter_preference
from app.preferences import PreferenceStore
from app.providers.base import AudioData
from app.schemas import Preference
from app.teachers import TeacherStore


ANALYSIS = {
    "language_features": ["短句、设问、强调逻辑连接"],
    "teaching_structure": ["问题、条件、推导、总结"],
    "thinking_patterns": ["先明确问题，再检查条件并演绎"],
    "rewrite_rules": ["先提出核心问题", "保留推导链条", "用清晰衔接词组织原文"],
    "avoid_features": ["不模仿无知识口头禅"],
    "evidence": ["先从问题出发"],
}


class PostASR:
    name = "post-asr"

    async def transcribe(self, content, filename, content_type):
        return "体积公等于外压乘以体积变化，我们先判断条件。"


class PostRewriter:
    name = "post-rewriter"

    async def proofread(self, text, context=""):
        return text.replace("体积公", "体积功")

    async def rewrite_post_course(self, text, preference, context=""):
        assert preference.mode == "style"
        assert "先提出核心问题" in preference.style_prompt
        return "先判断条件：体积功等于外压乘以体积变化。"


class PostTTS:
    name = "post-tts"

    async def synthesize(self, text):
        return AudioData(content=b"RIFF-preset", content_type="audio/wav", extension=".wav")


class CloneTTS:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text, reference):
        self.calls.append((text, reference))
        return AudioData(content=b"RIFF-clone", content_type="audio/wav", extension=".wav")


def make_pipeline(tmp_path, clone=None):
    store = TeacherStore(tmp_path / "teachers.json")
    profile = store.create("user-a", "物理老师", "lesson.wav", "我们先判断条件。", ANALYSIS, "voice-sample", True)
    voice_dir = tmp_path / "voice_samples"
    voice_dir.mkdir(exist_ok=True)
    (voice_dir / "voice-sample.wav").write_bytes(b"teacher-reference")
    pipeline = VoicePipeline(
        PostASR(), PostRewriter(), PostTTS(), PreferenceStore(tmp_path / "preferences.json"),
        tmp_path / "audio", store, voice_dir=voice_dir, voice_clone=clone,
    )
    return pipeline, profile


def test_realtime_preference_never_uses_teacher_style():
    preference = Preference(mode="style", teacher_profile_id="teacher", teacher_profile_name="物理老师")
    realtime = realtime_filter_preference(preference)
    assert realtime.mode == "filter"
    assert realtime.teacher_profile_id == "teacher"


def test_post_course_preserves_full_style_flow_and_authorized_voice(tmp_path):
    clone = CloneTTS()
    pipeline, profile = make_pipeline(tmp_path, clone)

    async def collect():
        return [event async for event in pipeline.process_post_course_stream(
            "user-a", profile.profile_id, [b"course-chunk"], use_teacher_voice=True
        )]

    events = asyncio.run(collect())
    assert events[0]["realtime"] is False
    assert events[0]["teacher_voice"] is True
    segment = next(event for event in events if event["type"] == "segment")
    assert segment["corrected_text"].startswith("体积功")
    assert segment["processed_text"] == "先判断条件：体积功等于外压乘以体积变化。"
    assert segment["audio_urls"]
    assert clone.calls[0][1] == b"teacher-reference"
    assert events[-1]["type"] == "done"


def test_post_course_rejects_voice_clone_without_consent(tmp_path):
    pipeline, profile = make_pipeline(tmp_path, CloneTTS())
    client = TestClient(create_app(Settings.from_env(), pipeline))
    response = client.post(
        "/v1/postprocess/course/stream",
        data={"user_id": "user-a", "profile_id": profile.profile_id, "use_teacher_voice": "true", "voice_consent": "false"},
        files={"file": ("lesson.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 403
    assert "授权" in response.json()["detail"]
