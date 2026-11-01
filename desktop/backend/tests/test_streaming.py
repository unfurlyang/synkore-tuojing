import asyncio
import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline import VoicePipeline, pop_stream_sentence
from app.preferences import PreferenceStore
from app.providers.base import AudioData
from app.providers.rules import RuleRewriter


class StreamingASR:
    name = "streaming-asr-test"

    async def transcribe_stream(self, content, filename, content_type):
        yield "体积公等于"
        yield "外压乘以体积变化。"


class StreamingRewriter:
    name = "streaming-rewrite-test"

    async def rewrite_stream(self, text, preference, context=""):
        assert "同音错别字" not in text
        yield "体积功等于外压"
        yield "乘以体积变化。"


class StreamingTTS:
    name = "streaming-tts-test"

    async def synthesize_stream(self, text):
        assert text == "体积功等于外压乘以体积变化。"
        yield b"\x01\x00\x02\x00"
        yield b"\x03\x00\x04\x00"


def make_pipeline(tmp_path):
    return VoicePipeline(
        StreamingASR(), StreamingRewriter(), StreamingTTS(),
        PreferenceStore(tmp_path / "preferences.json"), tmp_path / "audio",
    )


def test_pop_stream_sentence_keeps_partial_text():
    sentence, rest = pop_stream_sentence("体积功等于外压乘以体积变化。下一句话")
    assert sentence == "体积功等于外压乘以体积变化。"
    assert rest == "下一句话"
    assert pop_stream_sentence("尚未结束") == ("", "尚未结束")


def test_pipeline_streams_text_before_pcm_audio(tmp_path):
    pipeline = make_pipeline(tmp_path)

    async def collect():
        return [event async for event in pipeline.process_audio_stream(
            "user-a", b"audio", "clip.wav", "audio/wav", "realtime"
        )]

    events = asyncio.run(collect())
    types = [event["type"] for event in events]
    assert types.index("transcript_delta") < types.index("text_delta") < types.index("audio")
    assert events[-1]["type"] == "done"
    assert events[-1]["timings_ms"]["first_text"] is not None
    assert events[-1]["timings_ms"]["first_audio"] is not None
    audio_events = [event for event in events if event["type"] == "audio"]
    assert len(audio_events) == 2
    assert all(event["encoding"] == "pcm16le" and event["sample_rate"] == 24000 for event in audio_events)
    segment = next(event for event in events if event["type"] == "segment_done")
    assert segment["processed_text"] == "体积功等于外压乘以体积变化。"
    assert segment["fact_check_passed"] is True


def test_ndjson_streaming_audio_api(tmp_path):
    client = TestClient(create_app(Settings.from_env(), make_pipeline(tmp_path)))
    response = client.post(
        "/v1/process/audio/stream",
        data={"user_id": "user-a", "mode": "realtime"},
        files={"file": ("clip.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "start"
    assert events[0]["proofreading"] is True
    assert events[-1]["type"] == "done"


def test_non_streaming_providers_remain_compatible(tmp_path):
    class ASR:
        name = "plain"

        async def transcribe(self, content, filename, content_type):
            return "周五之前提交3份报告。"

    class TTS:
        name = "plain"

        async def synthesize(self, text):
            return AudioData(content=b"RIFF-test", content_type="audio/wav", extension=".wav")

    pipeline = VoicePipeline(ASR(), RuleRewriter(), TTS(), PreferenceStore(tmp_path / "p.json"), tmp_path / "audio")

    async def collect():
        return [event async for event in pipeline.process_audio_stream(
            "user-a", b"audio", "clip.wav", "audio/wav", "realtime"
        )]

    events = asyncio.run(collect())
    assert any(event["type"] == "audio_file" for event in events)
    assert events[-1]["type"] == "done"
