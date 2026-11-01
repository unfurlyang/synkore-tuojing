from __future__ import annotations

import re

from app.schemas import Preference

FILLERS = ("嗯嗯", "呃呃", "那个那个", "就是说", "那个", "嗯", "呃", "啊")


class RuleRewriter:
    """Explicit text-only fallback; never presented as a cloud model result."""

    name = "rules"

    async def rewrite(self, text: str, preference: Preference, context: str = "") -> str:
        result = text.strip()
        for filler in FILLERS:
            result = re.sub(rf"(?:^|[，,、\s]){re.escape(filler)}(?=[，,、\s]|$)", " ", result)
        result = re.sub(r"\b(\w+)\s+\1\b", r"\1", result, flags=re.IGNORECASE)
        result = re.sub(r"([一-鿿]{1,2})\1(?=，|,|。|！|!|？|\?)", r"\1", result)
        result = re.sub(r"\s*([，。！？；：,.!?;:])\s*", r"\1", result)
        result = re.sub(r"\s+", " ", result).strip(" ，,")
        return result or text.strip()


class NoTTS:
    name = "none"

    async def synthesize(self, text: str) -> None:
        return None
