import asyncio
import base64
import json

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.mimo import MimoASR, MimoRewriter, MimoTTS, MimoVoiceCloneTTS
from app.schemas import Preference

BASE_URL = "https://api.xiaomimimo.com/v1"


def test_mimo_asr_uses_official_chat_audio_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == f"{BASE_URL}/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["model"] == "mimo-v2.5-asr"
        assert payload["asr_options"] == {"language": "zh"}
        data = payload["messages"][0]["content"][0]["input_audio"]["data"]
        assert data.startswith("data:audio/wav;base64,")
        assert base64.b64decode(data.split(",", 1)[1]) == b"new-audio"
        return httpx.Response(200, json={"choices": [{"message": {"content": "周五之前提交3份报告。"}}]})

    provider = MimoASR(BASE_URL, "test-key", "mimo-v2.5-asr", "zh", 60, httpx.MockTransport(handler))
    text = asyncio.run(provider.transcribe(b"new-audio", "new.wav", "audio/wav"))
    assert text == "周五之前提交3份报告。"


def test_mimo_rewriter_uses_latest_flash_model():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "mimo-v2.6-flash"
        assert payload["response_format"] == {"type": "json_object"}
        content = json.dumps({"rewritten_text": "周五之前提交3份报告。"}, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = MimoRewriter(BASE_URL, "test-key", "mimo-v2.6-flash", 60, httpx.MockTransport(handler))
    text = asyncio.run(provider.rewrite("嗯，周五之前提交3份报告。", Preference()))
    assert text == "周五之前提交3份报告。"


def test_mimo_strong_filter_prompt_targets_non_knowledge():
    provider = MimoRewriter(BASE_URL, "test-key", "mimo-v2.6-flash", 60)
    preference = Preference(filter_strength="strong")
    prompt = provider._messages("大家学习热情高涨。压强等于压力除以受力面积。", preference)[0]["content"]
    assert "大家学习热情高涨" in prompt
    assert "只保留学科知识" in prompt
    assert "定义、概念、公式、原理" in prompt
    assert "空字符串" in prompt


def test_mimo_strong_filter_allows_empty_non_knowledge_segment():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"rewritten_text": ""})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = MimoRewriter(BASE_URL, "test-key", "mimo-v2.6-flash", 60, httpx.MockTransport(handler))
    text = asyncio.run(provider.rewrite("大家学习热情高涨。", Preference(filter_strength="strong")))
    assert text == ""


def test_mimo_style_mode_filters_then_transfers_in_one_request():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        assert "两个内部步骤" in prompt
        assert "第一步" in prompt and "第二步" in prompt
        assert "知识-only 强过滤" in prompt
        assert "目标教师画像：物理老师" in prompt
        assert "原文是疑问句时只清理并保留疑问，不得回答" in prompt
        assert "公式、变量关系和成立条件本身就是知识" in prompt
        assert payload["reasoning"] == {"effort": "none"}
        content = json.dumps({"rewritten_text": "先判断条件，再看压强公式。"}, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = MimoRewriter(BASE_URL, "test-key", "mimo-v2.6-flash", 60, httpx.MockTransport(handler))
    preference = Preference(mode="style", style_prompt="目标教师画像：物理老师")
    text = asyncio.run(provider.rewrite("大家很热情。压强等于压力除以面积。", preference))
    assert text == "先判断条件，再看压强公式。"


def test_mimo_short_segment_receives_read_only_course_context():
    provider = MimoRewriter(BASE_URL, "test-key", "mimo-v2.6-flash", 60)
    messages = provider._messages("那为什么它没有做功呢？", Preference(), "前面讨论活塞与压力。那为什么它没有做功呢？")
    assert "只用于理解指代和消歧" in messages[1]["content"]
    assert "唯一待处理短段" in messages[1]["content"]


def test_mimo_tts_places_target_text_in_assistant_message():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "mimo-v2.5-tts"
        assert payload["messages"][1] == {"role": "assistant", "content": "周五之前提交3份报告。"}
        assert payload["audio"] == {"format": "wav", "voice": "mimo_default"}
        audio = base64.b64encode(b"RIFF-cloud-audio").decode("ascii")
        return httpx.Response(200, json={"choices": [{"message": {"audio": {"data": audio}}}]})

    provider = MimoTTS(BASE_URL, "test-key", "mimo-v2.5-tts", "mimo_default", 60, httpx.MockTransport(handler))
    audio = asyncio.run(provider.synthesize("周五之前提交3份报告。"))
    assert audio.content == b"RIFF-cloud-audio"
    assert audio.extension == ".wav"


def test_mimo_never_silently_falls_back_without_key():
    provider = MimoASR(BASE_URL, "", "mimo-v2.5-asr", "zh", 60)
    with pytest.raises(ProviderError, match="MIMO_API_KEY"):
        asyncio.run(provider.transcribe(b"audio", "new.wav", "audio/wav"))


def test_mimo_streaming_rewrite_outputs_plain_text_with_proofreading_rules():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert "response_format" not in payload
        prompt = payload["messages"][0]["content"]
        assert "同音错别字" in prompt
        assert "只输出最终播报正文" in prompt
        body = (
            'data: {"choices":[{"delta":{"content":"体积功"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"等于外压乘以体积变化。"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    provider = MimoRewriter(BASE_URL, "test-key", "mimo-v2.6-flash", 60, httpx.MockTransport(handler))

    async def collect():
        return "".join([delta async for delta in provider.rewrite_stream("体积功等于外压乘以体积变化。", Preference())])

    assert asyncio.run(collect()) == "体积功等于外压乘以体积变化。"


def test_mimo_streaming_asr_yields_delta_text():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        body = (
            'data: {"choices":[{"delta":{"content":"压强"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"等于压力除以面积"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    provider = MimoASR(BASE_URL, "test-key", "mimo-v2.5-asr", "zh", 60, httpx.MockTransport(handler))

    async def collect():
        return [delta async for delta in provider.transcribe_stream(b"audio", "new.wav", "audio/wav")]

    assert asyncio.run(collect()) == ["压强", "等于压力除以面积"]


def test_mimo_streaming_tts_yields_official_pcm16_chunks():
    first = base64.b64encode(b"\x01\x00\x02\x00").decode("ascii")
    second = base64.b64encode(b"\x03\x00").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["audio"] == {"format": "pcm16", "voice": "mimo_default"}
        body = (
            f'data: {{"choices":[{{"delta":{{"audio":{{"data":"{first}"}}}}}}]}}\n\n'
            f'data: {{"choices":[{{"delta":{{"audio":{{"data":"{second}"}}}}}}]}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    provider = MimoTTS(BASE_URL, "test-key", "mimo-v2.5-tts", "mimo_default", 60, httpx.MockTransport(handler))

    async def collect():
        return [chunk async for chunk in provider.synthesize_stream("体积功。")]

    assert asyncio.run(collect()) == [b"\x01\x00\x02\x00", b"\x03\x00"]


def test_voiceclone_uses_reference_audio_for_offline_synthesis():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "mimo-v2.5-tts-voiceclone"
        assert payload["messages"][0]["role"] == 'user'
        assert '逐字朗读' in payload["messages"][0]['content']
        assert payload["messages"][1]["content"] == "完整课程风格转化。"
        voice = payload["audio"]["voice"]
        assert voice.startswith("data:audio/wav;base64,")
        assert base64.b64decode(voice.split(",", 1)[1]) == b"teacher-reference"
        audio = base64.b64encode(b"RIFF-cloned").decode("ascii")
        return httpx.Response(200, json={"choices": [{"message": {"audio": {"data": audio}}}]})

    provider = MimoVoiceCloneTTS(BASE_URL, "test-key", 60, httpx.MockTransport(handler))
    audio = asyncio.run(provider.synthesize("完整课程风格转化。", b"teacher-reference"))
    assert audio.content == b"RIFF-cloned"
