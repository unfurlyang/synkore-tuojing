from __future__ import annotations

from dataclasses import dataclass
from collections.abc import AsyncIterator
from typing import Protocol

from app.schemas import Preference


class ProviderError(RuntimeError):
    """A sanitized, actionable provider failure."""


@dataclass(frozen=True)
class AudioData:
    content: bytes
    content_type: str
    extension: str


class ASRProvider(Protocol):
    name: str

    async def transcribe(self, content: bytes, filename: str, content_type: str) -> str: ...

    def transcribe_stream(self, content: bytes, filename: str, content_type: str) -> AsyncIterator[str]: ...


class RewriteProvider(Protocol):
    name: str

    async def rewrite(self, text: str, preference: Preference, context: str = "") -> str: ...

    def rewrite_stream(self, text: str, preference: Preference, context: str = "") -> AsyncIterator[str]: ...


class TTSProvider(Protocol):
    name: str

    async def synthesize(self, text: str) -> AudioData | None: ...

    def synthesize_stream(self, text: str) -> AsyncIterator[bytes]: ...
