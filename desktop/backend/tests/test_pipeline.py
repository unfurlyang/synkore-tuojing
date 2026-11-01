import asyncio

from app.pipeline import VoicePipeline
from app.preferences import PreferenceStore
from app.providers.base import AudioData
from app.providers.rules import RuleRewriter
from app.schemas import InputMode


class FakeASR:
    name = "fake-asr-test"

    async def transcribe(self, content: bytes, filename: str, content_type: str) -> str:
        assert content == b"new-audio"
        return "嗯，项目可能在周五之前不能完成。第二段保留3个数字。"


class FakeTTS:
    name = "fake-tts-test"

    async def synthesize(self, text: str) -> AudioData:
        return AudioData(content=b"RIFF-test", content_type="audio/wav", extension=".wav")


class BadRewriter:
    name = "bad-rewriter-test"

    async def rewrite(self, text: str, preference, context: str = "") -> str:
        return "项目一定可以完成。"


def make_pipeline(tmp_path, rewriter=None):
    return VoicePipeline(
        asr=FakeASR(),
        rewriter=rewriter or RuleRewriter(),
        tts=FakeTTS(),
        preferences=PreferenceStore(tmp_path / "preferences.json"),
        audio_dir=tmp_path / "audio",
    )


def test_audio_pipeline_preserves_original_and_returns_segment_audio(tmp_path):
    pipeline = make_pipeline(tmp_path)
    response = asyncio.run(pipeline.process_audio("user-a", b"new-audio", "new.wav", "audio/wav", InputMode.playback))

    assert len(response.segments) == 2
    assert response.segments[0].original_text.startswith("嗯")
    assert response.segments[0].processed_text.startswith("项目")
    assert all(segment.audio_url for segment in response.segments)
    assert all(segment.timings_ms["asr_total"] >= 0 for segment in response.segments)
    assert response.degraded  # Rules are explicitly labelled as a degraded path.


class EmptyRewriter:
    name = "empty-rewriter-test"

    async def rewrite(self, text, preference, context=""):
        return ""


def test_strong_filter_drops_non_knowledge_without_audio_or_fallback(tmp_path):
    pipeline = make_pipeline(tmp_path, EmptyRewriter())
    response = asyncio.run(pipeline.process_text("user-a", "大家学习热情高涨。", InputMode.realtime))
    segment = response.segments[0]

    assert segment.processed_text == ""
    assert segment.audio_url is None
    assert segment.fact_check_passed
    assert not response.degraded
    assert "本段无可保留知识，已过滤" in segment.warnings


def test_strong_filter_never_drops_formula_when_model_returns_empty(tmp_path):
    pipeline = make_pipeline(tmp_path, EmptyRewriter())
    response = asyncio.run(pipeline.process_text("user-a", "然后我们说的这个是 P外乘以 delta V。", InputMode.realtime))
    segment = response.segments[0]
    assert "P外" in segment.processed_text
    assert "delta V" in segment.processed_text
    assert segment.audio_url
    assert response.degraded


def test_fallback_removes_nonknowledge_clauses_from_mixed_sentence(tmp_path):
    pipeline = make_pipeline(tmp_path, BadRewriter())
    response = asyncio.run(pipeline.process_text("user-a", "大家学习热情高涨，然后会有一些问题，体积功等于P外乘以delta V，不能省略外压。", InputMode.realtime))
    segment = response.segments[0]
    assert "学习热情" not in segment.processed_text
    assert "体积功" in segment.processed_text


def test_fact_failure_falls_back_to_original(tmp_path):
    pipeline = make_pipeline(tmp_path, BadRewriter())
    response = asyncio.run(pipeline.process_text("user-a", "项目可能在周五之前不能完成。", InputMode.realtime))
    segment = response.segments[0]

    assert segment.processed_text == segment.original_text
    assert not segment.fact_check_passed
    assert any(item.startswith("已回退原文") for item in segment.warnings)
    assert segment.audio_url
