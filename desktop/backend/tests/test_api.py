from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline import VoicePipeline
from app.preferences import PreferenceStore
from app.providers.base import AudioData
from app.providers.rules import RuleRewriter


class FakeASR:
    name = "fake-asr-test"

    async def transcribe(self, content, filename, content_type):
        return "嗯，周五之前提交3份报告。"


class FakeTTS:
    name = "fake-tts-test"

    async def synthesize(self, text):
        return AudioData(content=b"RIFF-test", content_type="audio/wav", extension=".wav")


def test_audio_api_and_generated_audio_download(tmp_path):
    pipeline = VoicePipeline(FakeASR(), RuleRewriter(), FakeTTS(), PreferenceStore(tmp_path / "p.json"), tmp_path / "audio")
    client = TestClient(create_app(Settings.from_env(), pipeline))

    response = client.post(
        "/v1/process/audio",
        data={"user_id": "user-a", "mode": "realtime"},
        files={"file": ("new.wav", b"new-audio", "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["providers"]["asr"] == "fake-asr-test"
    assert body["segments"][0]["original_text"] == "嗯，周五之前提交3份报告。"

    audio_url = body["segments"][0]["audio_url"]
    audio_response = client.get(audio_url)
    assert audio_response.status_code == 200
    assert audio_response.content == b"RIFF-test"


def test_m4a_is_converted_before_asr(tmp_path, monkeypatch):
    pipeline = VoicePipeline(FakeASR(), RuleRewriter(), FakeTTS(), PreferenceStore(tmp_path / "p.json"), tmp_path / "audio")
    client = TestClient(create_app(Settings.from_env(), pipeline))
    calls = []

    async def fake_convert(content, start, duration):
        calls.append((content, start, duration))
        return b"converted-wav"

    monkeypatch.setattr("app.main.convert_m4a_clip_to_wav", fake_convert)
    response = client.post(
        "/v1/process/audio",
        data={"user_id": "user-a", "mode": "playback", "start_seconds": 12, "duration_seconds": 30},
        files={"file": ("lesson.m4a", b"m4a-content", "audio/mp4")},
    )
    assert response.status_code == 200, response.text
    assert calls == [(b"m4a-content", 12.0, 30.0)]
    assert any("第 12–42 秒" in warning for warning in response.json()["warnings"])


def test_rejects_unsupported_audio(tmp_path):
    pipeline = VoicePipeline(FakeASR(), RuleRewriter(), FakeTTS(), PreferenceStore(tmp_path / "p.json"), tmp_path / "audio")
    client = TestClient(create_app(Settings.from_env(), pipeline))
    response = client.post(
        "/v1/process/audio",
        data={"user_id": "user-a"},
        files={"file": ("bad.exe", b"not-audio", "application/octet-stream")},
    )
    assert response.status_code == 415
