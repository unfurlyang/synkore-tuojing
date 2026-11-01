from __future__ import annotations

import re
from collections import Counter

from app.schemas import FactCheckResult

URL_EMAIL_RE = re.compile(r"(?:https?://[^\s，。；]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})")
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:%|％)?")
CHINESE_NUMBER_RE = re.compile(r"(?:[零〇二两三四五六七八九十百千万亿]+|一[十百千万亿]+)(?=[个段份次条章节课年月日周天小时分钟秒元块毛钱公里米千克克斤])")
WEEKDAY_RE = re.compile(r"周[一二三四五六日天末]")
LATIN_RE = re.compile(r"(?<![A-Za-z0-9_.-])[A-Za-z][A-Za-z0-9_.-]*(?![A-Za-z0-9_.-])")
NEGATIONS = ("不能", "不会", "不要", "没有", "未必", "不", "未", "无", "禁止", "拒绝")
UNCERTAINTIES = ("可能", "预计", "大概", "建议", "未必", "或许", "不一定", "暂时")
SCOPES = ("之前", "之后", "至少", "最多", "不超过", "以上", "以下", "以内", "以外")


def _markers(text: str) -> dict[str, list[str]]:
    text = text.replace("德尔塔", " delta ").replace("Δ", " delta ").replace("δ", " delta ")
    # ASR may split one formula symbol into letters: W e and We are equivalent.
    text = re.sub(
        r"(?<![A-Za-z])(?:[A-Za-z]\s+)+[A-Za-z](?![A-Za-z])",
        lambda match: re.sub(r"\s+", "", match.group(0)),
        text,
    )
    return {
        "url_email": URL_EMAIL_RE.findall(text),
        "number": NUMBER_RE.findall(text) + CHINESE_NUMBER_RE.findall(text) + WEEKDAY_RE.findall(text),
        "latin": LATIN_RE.findall(text),
        "negation": [word for word in NEGATIONS if word in text],
        "uncertainty": [word for word in UNCERTAINTIES if word in text],
        "scope": [word for word in SCOPES if word in text],
    }


def check_facts(original: str, candidate: str, allow_missing_categories=frozenset()) -> FactCheckResult:
    if not candidate.strip():
        return FactCheckResult(accepted=False, missing=["空候选文本"], introduced=[])

    before = _markers(original)
    after = _markers(candidate)
    missing: list[str] = []
    introduced: list[str] = []

    for category in ("url_email", "number", "latin"):
        before_values = set(before[category]) if category == "latin" else before[category]
        after_values = set(after[category]) if category == "latin" else after[category]
        before_counts = Counter(before_values)
        after_counts = Counter(after_values)
        if category not in allow_missing_categories:
            missing.extend(f"{category}:{item}" for item in (before_counts - after_counts).elements())
        introduced.extend(f"{category}:{item}" for item in (after_counts - before_counts).elements())

    for category in ("negation", "uncertainty", "scope"):
        before_set = set(before[category])
        after_set = set(after[category])
        if category not in allow_missing_categories:
            missing.extend(f"{category}:{item}" for item in sorted(before_set - after_set))
        introduced.extend(f"{category}:{item}" for item in sorted(after_set - before_set))

    introduced = [
        item for item in introduced
        if not (
            item.startswith("latin:")
            and re.fullmatch(r"[A-Za-z]", item[6:])
            and re.search(rf"(?<![A-Za-z]){re.escape(item[6:])}\s*=", candidate)
        )
    ]

    return FactCheckResult(accepted=not missing and not introduced, missing=missing, introduced=introduced)
