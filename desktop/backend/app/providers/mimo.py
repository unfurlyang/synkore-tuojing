from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from app.providers.base import AudioData, ProviderError
from app.providers.openai_compatible import OpenAICompatibleRewriter, OpenAICompatibleTeacherProfiler, _error_message


def _check_key(api_key: str, provider: str) -> None:
    if not api_key or api_key == "replace_me":
        raise ProviderError(f"{provider} 已选择小米云端，但未配置 MIMO_API_KEY")


class MimoASR:
    name = "mimo"

    def __init__(self, base_url: str, api_key: str, model: str, language: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        self.configured = bool(api_key and api_key != "replace_me")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.language = language
        self.timeout = timeout
        self.transport = transport

    async def transcribe(self, content: bytes, filename: str, content_type: str) -> str:
        _check_key(self.api_key, "ASR_PROVIDER=mimo")
        extension = Path(filename).suffix.lower()
        if extension not in {".wav", ".mp3"}:
            raise ProviderError("小米 mimo-v2.5-asr 仅支持 WAV 和 MP3 输入")
        encoded = base64.b64encode(content).decode("ascii")
        if len(encoded.encode("ascii")) > 10 * 1024 * 1024:
            raise ProviderError("音频 Base64 编码后超过小米 ASR 的 10 MB 限制")
        mime_type = "audio/wav" if extension == ".wav" else "audio/mpeg"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": f"data:{mime_type};base64,{encoded}"},
                        }
                    ],
                }
            ],
            "asr_options": {"language": self.language},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()
            if not text:
                raise ProviderError("小米 ASR 返回了空文本")
            return text
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError(_error_message("小米语音识别", exc)) from exc

    async def transcribe_stream(self, content: bytes, filename: str, content_type: str) -> AsyncIterator[str]:
        """Stream transcript deltas for one short uploaded clip; input audio is not a live socket."""
        _check_key(self.api_key, "ASR_PROVIDER=mimo")
        extension = Path(filename).suffix.lower()
        if extension not in {".wav", ".mp3"}:
            raise ProviderError("小米 mimo-v2.5-asr 仅支持 WAV 和 MP3 输入")
        encoded = base64.b64encode(content).decode("ascii")
        if len(encoded.encode("ascii")) > 10 * 1024 * 1024:
            raise ProviderError("音频 Base64 编码后超过小米 ASR 的 10 MB 限制")
        mime_type = "audio/wav" if extension == ".wav" else "audio/mpeg"
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [{"type": "input_audio", "input_audio": {"data": f"data:{mime_type};base64,{encoded}"}}],
            }],
            "asr_options": {"language": self.language},
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        chunk = json.loads(data)
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        text = (choices[0].get("delta") or {}).get("content")
                        if isinstance(text, str) and text:
                            yield text
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("小米流式语音识别", exc)) from exc


class MimoRewriter(OpenAICompatibleRewriter):
    name = "mimo"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        self.configured = bool(api_key and api_key != "replace_me")
        super().__init__(base_url, api_key or "replace_me", model, timeout, transport)

    def _request_extras(self) -> dict:
        return {"reasoning": {"effort": "none"}}

    async def rewrite(self, text: str, preference, context: str = "") -> str:
        _check_key(self.api_key, "REWRITE_PROVIDER=mimo")
        return await super().rewrite(text, preference, context)

    async def rewrite_stream(self, text: str, preference, context: str = "") -> AsyncIterator[str]:
        _check_key(self.api_key, "REWRITE_PROVIDER=mimo")
        async for delta in super().rewrite_stream(text, preference, context):
            yield delta

    async def proofread(self, text: str, context: str = "") -> str:
        _check_key(self.api_key, "REWRITE_PROVIDER=mimo")
        return await super().proofread(text, context)

    async def rewrite_post_course(self, text: str, preference, context: str = "") -> str:
        _check_key(self.api_key, "REWRITE_PROVIDER=mimo")
        return await super().rewrite_post_course(text, preference, context)


class MimoTeacherProfiler(OpenAICompatibleTeacherProfiler):
    name = "mimo"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        self.configured = bool(api_key and api_key != "replace_me")
        super().__init__(base_url, api_key or "replace_me", model, timeout, transport)

    def _request_extras(self) -> dict:
        return {"reasoning": {"effort": "none"}}

    async def distill(self, transcript: str, teacher_name: str) -> dict[str, list[str]]:
        _check_key(self.api_key, "REWRITE_PROVIDER=mimo")
        return await super().distill(transcript, teacher_name)


class MimoTTS:
    name = "mimo"

    def __init__(self, base_url: str, api_key: str, model: str, voice: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        self.configured = bool(api_key and api_key != "replace_me")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.timeout = timeout
        self.transport = transport

    async def synthesize(self, text: str) -> AudioData:
        _check_key(self.api_key, "TTS_PROVIDER=mimo")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "用清晰、自然、平稳的中文讲解语气，语速适中。逐字朗读 assistant 原文，不加开场白或语气词，不漏字、不换词，不改变数字、单位和否定。"},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "wav", "voice": self.voice},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            audio_data = response.json()["choices"][0]["message"]["audio"]["data"]
            content = base64.b64decode(audio_data)
            if not content:
                raise ProviderError("小米 TTS 返回了空音频")
            return AudioData(content=content, content_type="audio/wav", extension=".wav")
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError(_error_message("小米语音合成", exc)) from exc

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield official 24 kHz PCM16LE mono chunks as soon as MiMo returns them."""
        _check_key(self.api_key, "TTS_PROVIDER=mimo")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "用清晰、自然、平稳的中文讲解语气，语速适中。逐字朗读 assistant 原文，不加开场白或语气词，不漏字、不换词，不改变数字、单位和否定。"},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "pcm16", "voice": self.voice},
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        chunk = json.loads(data)
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        audio = (choices[0].get("delta") or {}).get("audio")
                        if isinstance(audio, dict) and audio.get("data"):
                            pcm = base64.b64decode(audio["data"])
                            if pcm:
                                yield pcm
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("小米流式语音合成", exc)) from exc


class MimoVoiceCloneTTS:
    """Authorized teacher-voice synthesis for offline course conversion only."""

    name = "mimo-voiceclone"

    def __init__(self, base_url: str, api_key: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        self.configured = bool(api_key and api_key != "replace_me")
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    async def synthesize(self, text: str, reference_wav: bytes) -> AudioData:
        _check_key(self.api_key, "TTS_PROVIDER=mimo-voiceclone")
        if not reference_wav:
            raise ProviderError("缺少教师声音参考样本")
        encoded = base64.b64encode(reference_wav).decode("ascii")
        if len(encoded.encode("ascii")) > 10 * 1024 * 1024:
            raise ProviderError("教师声音参考超过小米 voiceclone 的 10 MB Base64 限制")
        payload = {
            "model": "mimo-v2.5-tts-voiceclone",
            "messages": [
                {"role": "user", "content": "只逐字朗读 assistant 原文，不模仿参考样本的文案，不添加、重复或遗漏文字；数字、单位与否定必须准确。"},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "wav", "voice": f"data:audio/wav;base64,{encoded}"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            data = response.json()["choices"][0]["message"]["audio"]["data"]
            content = base64.b64decode(data)
            if not content:
                raise ProviderError("教师声音合成返回了空音频")
            return AudioData(content=content, content_type="audio/wav", extension=".wav")
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError(_error_message("教师声音合成", exc)) from exc
