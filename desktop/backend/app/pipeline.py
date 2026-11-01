from __future__ import annotations

import asyncio
import base64
import re
import time
import uuid
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from app.facts import check_facts
from app.preferences import PreferenceStore
from app.providers.base import ASRProvider, AudioData, ProviderError, RewriteProvider, TTSProvider
from app.schemas import InputMode, Preference, PreferenceUpdate, ProcessResponse, RewriteMode, SegmentResult, TeacherProfile
from app.teachers import TeacherStore, teacher_style_prompt


def split_text(text: str, max_length: int = 240) -> list[str]:
    text = text.strip()
    if not text:
        return []
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;\n])\s*", text) if item.strip()]
    segments: list[str] = []
    for sentence in sentences:
        while len(sentence) > max_length:
            cut = max(sentence.rfind(mark, 0, max_length) for mark in ("，", ",", " ", " "))
            cut = cut + 1 if cut > 30 else max_length
            segments.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            segments.append(sentence)
    return segments


def pop_stream_sentence(buffer: str, final: bool = False) -> tuple[str, str]:
    """Return one speakable clause without waiting for the whole model response."""
    if final:
        return buffer.strip(), ""
    for index, char in enumerate(buffer):
        if char in "。！？!?；;" and len(buffer[:index].strip()) >= 4:
            return buffer[: index + 1].strip(), buffer[index + 1 :]
    if len(buffer) >= 64:
        candidates = [buffer.rfind(mark, 24, 64) for mark in ("，", ",", "：", ":")]
        cut = max(candidates)
        if cut >= 24:
            return buffer[: cut + 1].strip(), buffer[cut + 1 :]
    return "", buffer


KNOWLEDGE_SIGNAL_RE = re.compile(
    r"[A-Za-z0-9Δδ]|定义|概念|公式|原理|因果|条件|推导|定律|方程|系统|环境|压力|压强|体积|活塞|气体|"
    r"做功|能量|力|速度|质量|温度|电流|电压|反应|函数|极限|证明|等于|大于|小于|因为|所以|因此|如果|为什么|"
    r"不能|不会|不要|没有|未必|项目|完成|提交|报告|预算"
)


def has_knowledge_signal(text: str) -> bool:
    return bool(KNOWLEDGE_SIGNAL_RE.search(text))


def knowledge_aware_fallback(text: str) -> str:
    clauses = re.findall(r"[^，。！？；]+[，。！？；]?", text)
    kept = [clause for clause in clauses if has_knowledge_signal(clause)]
    if kept:
        return conservative_fallback("".join(kept))
    return conservative_fallback(text)


def conservative_fallback(text: str) -> str:
    """Remove only obvious vocal fillers when a model candidate is unsafe."""
    cleaned = re.sub(r"[嗯呃]{1,2}[，,、\s]*", "", text)
    cleaned = re.sub(r"[，,、\s]*(?:对吧|是吧)(?=[。！？!?]|$)", "", cleaned)
    cleaned = re.sub(r"([一-鿿]{1,2})[，,、\s]+\1", r"\1", cleaned)
    cleaned = re.sub(r"\s*([，。！？；：,.!?;:])\s*", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ，,") or text.strip()


def realtime_filter_preference(preference: Preference) -> Preference:
    """Real-time listening is deliberately extraction-only; style transfer is post-course."""
    return preference.model_copy(update={"mode": RewriteMode.filter})


class VoicePipeline:
    def __init__(
        self,
        asr: ASRProvider,
        rewriter: RewriteProvider,
        tts: TTSProvider,
        preferences: PreferenceStore,
        audio_dir: Path,
        teacher_profiles: TeacherStore | None = None,
        teacher_profiler=None,
        voice_dir: Path | None = None,
        voice_clone=None,
    ):
        self.asr = asr
        self.rewriter = rewriter
        self.tts = tts
        self.preferences = preferences
        self.audio_dir = audio_dir
        self.teacher_profiles = teacher_profiles
        self.teacher_profiler = teacher_profiler
        self.voice_dir = voice_dir or audio_dir.parent / "voice_samples"
        self.voice_clone = voice_clone
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.voice_dir.mkdir(parents=True, exist_ok=True)

    @property
    def provider_names(self) -> dict[str, str]:
        return {"asr": self.asr.name, "rewrite": self.rewriter.name, "tts": self.tts.name}

    def _save_audio(self, audio: AudioData) -> str:
        filename = f"{uuid.uuid4().hex}{audio.extension}"
        path = self.audio_dir / filename
        path.write_bytes(audio.content)
        return f"/v1/audio/{filename}"

    async def _process_segment(self, segment_id: int, text: str, preference: Preference, context: str = "") -> SegmentResult:
        warnings: list[str] = []
        timings: dict[str, float] = {}
        candidate = ""
        processed = text
        fact_passed = True
        degraded = False

        started = time.perf_counter()
        try:
            candidate = await self.rewriter.rewrite(text, preference, context)
            timings["rewrite"] = round((time.perf_counter() - started) * 1000, 2)
            if preference.filter_strength == "strong" and not candidate.strip():
                if has_knowledge_signal(text):
                    processed = knowledge_aware_fallback(text)
                    fact_passed = False
                    degraded = True
                    warnings.append("模型可能误删知识，已保留原文中的知识片段")
                else:
                    processed = ""
                    fact_passed = True
                    warnings.append("本段无可保留知识，已过滤")
            else:
                allow_missing = {"number", "latin", "scope"} if preference.filter_strength == "strong" else set()
                fact = check_facts(text, candidate, allow_missing)
                fact_passed = fact.accepted
                if fact.accepted:
                    processed = candidate
                else:
                    processed = knowledge_aware_fallback(text) if preference.filter_strength == "strong" else conservative_fallback(text)
                    degraded = True
                    warnings.extend(fact.warnings)
                    warnings.append("已回退原文（仅清理明显口头词）")
        except ProviderError as exc:
            timings["rewrite"] = round((time.perf_counter() - started) * 1000, 2)
            fact_passed = False
            degraded = True
            warnings.extend([str(exc), "改写失败，已回退原文"])

        if self.rewriter.name == "rules":
            degraded = True
            warnings.append("当前为本地规则降级路径，不代表真实模型改写效果")

        if not processed:
            timings["tts"] = 0.0
            audio_url = None
        else:
            started = time.perf_counter()
            try:
                audio = await self.tts.synthesize(processed)
                timings["tts"] = round((time.perf_counter() - started) * 1000, 2)
                audio_url = self._save_audio(audio) if audio else None
                if audio is None:
                    degraded = True
                    warnings.append("未启用语音合成，当前仅返回文本")
            except ProviderError as exc:
                timings["tts"] = round((time.perf_counter() - started) * 1000, 2)
                audio_url = None
                degraded = True
                warnings.extend([str(exc), "文本结果仍可使用"])

        return SegmentResult(
            segment_id=segment_id,
            original_text=text,
            candidate_text=candidate,
            processed_text=processed,
            audio_url=audio_url,
            status="degraded" if degraded else "ok",
            preference_version=preference.version,
            fact_check_passed=fact_passed,
            warnings=warnings,
            timings_ms=timings,
        )

    async def process_text(
        self,
        user_id: str,
        text: str,
        mode: InputMode,
        preference: Preference | None = None,
    ) -> ProcessResponse:
        started = time.perf_counter()
        preference = realtime_filter_preference(preference or self.preferences.get(user_id))
        parts = split_text(text, max_length=100) if mode == InputMode.realtime else split_text(text)
        if not parts:
            raise ProviderError("没有可处理的文本")
        semaphore = asyncio.Semaphore(3)

        async def run_part(index: int, part: str) -> SegmentResult:
            context = text.strip() if len(text) <= 4000 else " ".join(parts[max(0, index - 2) : min(len(parts), index + 1)])
            async with semaphore:
                return await self._process_segment(index, part, preference, context)

        segments = list(await asyncio.gather(*(run_part(index, part) for index, part in enumerate(parts, start=1))))
        warnings: list[str] = []
        if self.rewriter.name == "rules":
            warnings.append("规则降级已明确标注；配置模型服务后才验证真实模型改写")
        return ProcessResponse(
            request_id=uuid.uuid4().hex,
            mode=mode,
            output_mode=preference.mode,
            teacher_profile_id=preference.teacher_profile_id,
            teacher_profile_name=preference.teacher_profile_name,
            segments=segments,
            providers=self.provider_names,
            degraded=any(item.status == "degraded" for item in segments),
            warnings=warnings,
            total_latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def process_audio(
        self,
        user_id: str,
        content: bytes,
        filename: str,
        content_type: str,
        mode: InputMode,
    ) -> ProcessResponse:
        started = time.perf_counter()
        preference = self.preferences.get(user_id)
        original_text = await self.asr.transcribe(content, filename, content_type)
        asr_ms = round((time.perf_counter() - started) * 1000, 2)
        response = await self.process_text(user_id, original_text, mode, preference)
        response.total_latency_ms = round(response.total_latency_ms + asr_ms, 2)
        for segment in response.segments:
            segment.timings_ms["asr_total"] = asr_ms
        return response

    def _save_pcm16(self, content: bytes) -> str:
        filename = f"{uuid.uuid4().hex}.wav"
        path = self.audio_dir / filename
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(content)
        return f"/v1/audio/{filename}"

    async def _stream_sentence(
        self,
        segment_id: int,
        sentence_id: int,
        text: str,
        original: str,
        started: float,
        first_audio: dict[str, float | None],
    ) -> AsyncIterator[dict]:
        """Check a streamed clause for introduced facts, then stream its PCM audio."""
        text = text.strip()
        if not text:
            return
        allow_missing = {"url_email", "number", "latin", "negation", "uncertainty", "scope"}
        fact = check_facts(original, text, allow_missing)
        base = {
            "segment_id": segment_id,
            "sentence_id": sentence_id,
            "text": text,
            "fact_check_passed": fact.accepted,
            "warnings": fact.warnings,
        }
        if not fact.accepted:
            yield {**base, "type": "sentence_done", "degraded": True, "audio_url": None}
            return
        yield {"type": "sentence", **base}
        pcm = bytearray()
        try:
            if hasattr(self.tts, "synthesize_stream"):
                async for chunk in self.tts.synthesize_stream(text):
                    if not chunk:
                        continue
                    pcm.extend(chunk)
                    if first_audio["ms"] is None:
                        first_audio["ms"] = round((time.perf_counter() - started) * 1000, 2)
                    yield {
                        "type": "audio",
                        "segment_id": segment_id,
                        "sentence_id": sentence_id,
                        "data": base64.b64encode(chunk).decode("ascii"),
                        "encoding": "pcm16le",
                        "sample_rate": 24000,
                        "channels": 1,
                        "first_audio_ms": first_audio["ms"],
                    }
                audio_url = self._save_pcm16(bytes(pcm)) if pcm else None
            else:
                audio = await self.tts.synthesize(text)
                audio_url = self._save_audio(audio) if audio else None
                if audio_url:
                    if first_audio["ms"] is None:
                        first_audio["ms"] = round((time.perf_counter() - started) * 1000, 2)
                    yield {"type": "audio_file", "segment_id": segment_id, "sentence_id": sentence_id, "url": audio_url}
            if not audio_url:
                raise ProviderError("流式合成未返回有效音频")
            yield {**base, "type": "sentence_done", "degraded": False, "audio_url": audio_url}
        except ProviderError as exc:
            yield {
                **base,
                "type": "sentence_done",
                "degraded": True,
                "audio_url": None,
                "warnings": [*fact.warnings, str(exc), "该句文本仍可使用"],
            }

    async def process_text_stream(
        self,
        user_id: str,
        text: str,
        mode: InputMode,
        preference: Preference | None = None,
        request_id: str | None = None,
        started: float | None = None,
    ) -> AsyncIterator[dict]:
        started = started or time.perf_counter()
        request_id = request_id or uuid.uuid4().hex
        preference = realtime_filter_preference(preference or self.preferences.get(user_id))
        first_audio: dict[str, float | None] = {"ms": None}
        first_text_ms: float | None = None
        degraded = False
        yield {
            "type": "start",
            "request_id": request_id,
            "mode": mode,
            "output_mode": preference.mode,
            "teacher_profile_id": preference.teacher_profile_id,
            "teacher_profile_name": preference.teacher_profile_name,
            "proofreading": True,
            "streaming": True,
        }
        parts = split_text(text, max_length=100) if mode == InputMode.realtime else split_text(text)
        if not parts:
            yield {"type": "error", "detail": "没有可处理的文本"}
            return
        try:
            for segment_id, part in enumerate(parts, start=1):
                context = text.strip() if len(text) <= 4000 else " ".join(
                    parts[max(0, segment_id - 2) : min(len(parts), segment_id + 1)]
                )
                candidate = ""
                pending = ""
                sentence_id = 0
                audio_count = 0
                segment_degraded = False
                warnings: list[str] = []
                try:
                    if hasattr(self.rewriter, "rewrite_stream"):
                        deltas = self.rewriter.rewrite_stream(part, preference, context)
                    else:
                        async def single_delta():
                            yield await self.rewriter.rewrite(part, preference, context)
                        deltas = single_delta()
                    async for delta in deltas:
                        if not delta:
                            continue
                        if first_text_ms is None:
                            first_text_ms = round((time.perf_counter() - started) * 1000, 2)
                        candidate += delta
                        pending += delta
                        yield {"type": "text_delta", "segment_id": segment_id, "text": delta, "first_text_ms": first_text_ms}
                        while True:
                            sentence, pending = pop_stream_sentence(pending)
                            if not sentence:
                                break
                            sentence_id += 1
                            async for event in self._stream_sentence(
                                segment_id, sentence_id, sentence, part, started, first_audio
                            ):
                                if event["type"] in {"audio", "audio_file"}:
                                    audio_count += 1
                                if event.get("degraded"):
                                    segment_degraded = True
                                yield event
                    sentence, pending = pop_stream_sentence(pending, final=True)
                    if sentence:
                        sentence_id += 1
                        async for event in self._stream_sentence(
                            segment_id, sentence_id, sentence, part, started, first_audio
                        ):
                            if event["type"] in {"audio", "audio_file"}:
                                audio_count += 1
                            if event.get("degraded"):
                                segment_degraded = True
                            yield event
                except ProviderError as exc:
                    segment_degraded = True
                    warnings.append(str(exc))

                candidate = candidate.strip()
                allow_missing = {"number", "latin", "scope"} if preference.filter_strength == "strong" else set()
                if preference.filter_strength == "strong" and not candidate:
                    if has_knowledge_signal(part):
                        processed = knowledge_aware_fallback(part)
                        fact_passed = False
                        segment_degraded = True
                        warnings.append("模型可能误删知识，已保留原文知识片段")
                    else:
                        processed = ""
                        fact_passed = True
                        warnings.append("本段无可保留知识，已过滤")
                else:
                    fact = check_facts(part, candidate, allow_missing)
                    fact_passed = fact.accepted
                    processed = candidate
                    if not fact.accepted:
                        segment_degraded = True
                        warnings.extend(fact.warnings)
                        if audio_count == 0:
                            processed = knowledge_aware_fallback(part) if preference.filter_strength == "strong" else conservative_fallback(part)
                            warnings.append("未播放候选内容，已改用安全清理文本")
                        else:
                            warnings.append("流式句子均已通过新增事实检查；整段复核存在遗漏差异")

                if processed and audio_count == 0:
                    sentence_id += 1
                    async for event in self._stream_sentence(
                        segment_id, sentence_id, processed, part, started, first_audio
                    ):
                        if event["type"] in {"audio", "audio_file"}:
                            audio_count += 1
                        if event.get("degraded"):
                            segment_degraded = True
                        yield event
                degraded = degraded or segment_degraded
                yield {
                    "type": "segment_done",
                    "segment_id": segment_id,
                    "original_text": part,
                    "candidate_text": candidate,
                    "processed_text": processed,
                    "fact_check_passed": fact_passed,
                    "degraded": segment_degraded,
                    "warnings": warnings,
                    "audio_started": audio_count > 0,
                }
            yield {
                "type": "done",
                "request_id": request_id,
                "degraded": degraded,
                "timings_ms": {
                    "first_text": first_text_ms,
                    "first_audio": first_audio["ms"],
                    "total": round((time.perf_counter() - started) * 1000, 2),
                },
            }
        except ProviderError as exc:
            yield {"type": "error", "request_id": request_id, "detail": str(exc)}

    async def process_audio_stream(
        self,
        user_id: str,
        content: bytes,
        filename: str,
        content_type: str,
        mode: InputMode,
    ) -> AsyncIterator[dict]:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        preference = realtime_filter_preference(self.preferences.get(user_id))
        yield {
            "type": "start",
            "request_id": request_id,
            "mode": mode,
            "output_mode": preference.mode,
            "teacher_profile_id": preference.teacher_profile_id,
            "teacher_profile_name": preference.teacher_profile_name,
            "proofreading": True,
            "streaming": True,
            "asr_input": "short_clip",
        }
        transcript_parts: list[str] = []
        try:
            if hasattr(self.asr, "transcribe_stream"):
                async for delta in self.asr.transcribe_stream(content, filename, content_type):
                    if delta:
                        transcript_parts.append(delta)
                        yield {"type": "transcript_delta", "text": delta}
                transcript = "".join(transcript_parts).strip()
            else:
                transcript = (await self.asr.transcribe(content, filename, content_type)).strip()
                yield {"type": "transcript_delta", "text": transcript}
            if not transcript:
                raise ProviderError("语音识别没有返回文本")
            asr_ms = round((time.perf_counter() - started) * 1000, 2)
            yield {"type": "transcript", "text": transcript, "asr_ms": asr_ms}
            async for event in self.process_text_stream(
                user_id, transcript, mode, preference, request_id=request_id, started=started
            ):
                if event["type"] == "start":
                    continue
                if event["type"] == "done":
                    event["timings_ms"]["asr"] = asr_ms
                yield event
        except ProviderError as exc:
            yield {"type": "error", "request_id": request_id, "detail": str(exc)}

    async def _proofread_transcript(self, transcript: str) -> str:
        if not hasattr(self.rewriter, "proofread"):
            return transcript
        chunks = split_text(transcript, max_length=3000) or [transcript]
        semaphore = asyncio.Semaphore(2)

        async def run(index: int, chunk: str) -> tuple[int, str]:
            async with semaphore:
                try:
                    corrected = await self.rewriter.proofread(chunk, transcript[:500])
                    fact = check_facts(chunk, corrected)
                    return index, corrected if fact.accepted else chunk
                except ProviderError:
                    return index, chunk

        corrected_chunks = await asyncio.gather(*(run(index, chunk) for index, chunk in enumerate(chunks)))
        return "".join(chunk for _, chunk in sorted(corrected_chunks)).strip() or transcript

    async def distill_teacher_text(
        self,
        user_id: str,
        teacher_name: str,
        transcript: str,
        source_filename: str = "text",
        voice_sample_id: str | None = None,
        voice_consent: bool = False,
    ) -> TeacherProfile:
        if not self.teacher_profiles or not self.teacher_profiler:
            raise ProviderError("当前服务未配置教师画像蒸馏模型")
        if len(transcript.strip()) < 20:
            raise ProviderError("有效课程内容太短，请至少录入约 20 个字；更长的样本能得到更稳定的画像")
        corrected_transcript = await self._proofread_transcript(transcript.strip())
        analysis = await self.teacher_profiler.distill(corrected_transcript, teacher_name.strip())
        return self.teacher_profiles.create(
            user_id, teacher_name.strip(), source_filename, corrected_transcript, analysis,
            voice_sample_id=voice_sample_id, voice_consent=voice_consent,
        )

    async def distill_teacher_audio(
        self,
        user_id: str,
        teacher_name: str,
        chunks: list[bytes],
        source_filename: str,
        voice_consent: bool = False,
    ) -> TeacherProfile:
        if not chunks:
            raise ProviderError("没有可用于教师画像的音频片段")
        semaphore = asyncio.Semaphore(3)

        async def transcribe(index: int, content: bytes) -> tuple[int, str]:
            async with semaphore:
                text = await self.asr.transcribe(content, f"teacher-{index:03d}.wav", "audio/wav")
                return index, text

        results = await asyncio.gather(*(transcribe(index, content) for index, content in enumerate(chunks, start=1)))
        transcript = "\n".join(text for _, text in sorted(results))
        voice_sample_id = None
        if voice_consent:
            voice_sample_id = uuid.uuid4().hex
            (self.voice_dir / f"{voice_sample_id}.wav").write_bytes(chunks[0])
        return await self.distill_teacher_text(
            user_id, teacher_name, transcript, source_filename,
            voice_sample_id=voice_sample_id, voice_consent=voice_consent,
        )

    async def process_post_course_stream(
        self,
        user_id: str,
        profile_id: str,
        chunks: list[bytes],
        use_teacher_voice: bool = False,
    ) -> AsyncIterator[dict]:
        """Offline full-course style transfer with optional authorized teacher timbre."""
        started = time.perf_counter()
        if not self.teacher_profiles:
            raise ProviderError("当前服务未配置教师画像存储")
        profile = self.teacher_profiles.get(user_id, profile_id)
        if use_teacher_voice:
            if not self.voice_clone or not profile.voice_consent or not profile.voice_sample_id:
                raise ProviderError("该画像没有已授权的教师声音参考，请重新录入并明确授权")
        reference = (
            (self.voice_dir / f"{profile.voice_sample_id}.wav").read_bytes()
            if use_teacher_voice and profile.voice_sample_id else b""
        )
        preference = Preference(mode=RewriteMode.style, style_prompt=teacher_style_prompt(profile))
        yield {
            "type": "start", "profile_id": profile.profile_id, "profile_name": profile.name,
            "total_chunks": len(chunks), "teacher_voice": use_teacher_voice, "realtime": False,
        }
        degraded = False
        for index, content in enumerate(chunks, start=1):
            chunk_started = time.perf_counter()
            yield {"type": "progress", "chunk": index, "total_chunks": len(chunks), "stage": "transcribing"}
            warnings: list[str] = []
            try:
                original = await self.asr.transcribe(content, f"course-{index:03d}.wav", "audio/wav")
                yield {"type": "progress", "chunk": index, "total_chunks": len(chunks), "stage": "proofreading"}
                corrected = await self._proofread_transcript(original)
                yield {"type": "progress", "chunk": index, "total_chunks": len(chunks), "stage": "style_transfer"}
                try:
                    transformed = await self.rewriter.rewrite_post_course(corrected, preference, corrected)
                    fact = check_facts(corrected, transformed, {"scope"})
                    if not fact.accepted:
                        transformed = corrected
                        degraded = True
                        warnings.extend([*fact.warnings, "风格候选未通过事实核对，本段保留校对原文"])
                except ProviderError as exc:
                    transformed = corrected
                    degraded = True
                    warnings.append(str(exc))
                audio_urls: list[str] = []
                for part in split_text(transformed, max_length=160):
                    try:
                        audio = (
                            await self.voice_clone.synthesize(part, reference)
                            if use_teacher_voice else await self.tts.synthesize(part)
                        )
                        if audio:
                            audio_urls.append(self._save_audio(audio))
                    except ProviderError as exc:
                        degraded = True
                        warnings.append(str(exc))
                yield {
                    "type": "segment", "chunk": index, "total_chunks": len(chunks),
                    "original_text": original, "corrected_text": corrected, "processed_text": transformed,
                    "audio_urls": audio_urls, "teacher_voice": use_teacher_voice,
                    "degraded": bool(warnings), "warnings": warnings,
                    "latency_ms": round((time.perf_counter() - chunk_started) * 1000, 2),
                }
            except ProviderError as exc:
                degraded = True
                yield {"type": "segment_error", "chunk": index, "total_chunks": len(chunks), "detail": str(exc)}
        yield {
            "type": "done", "degraded": degraded,
            "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def select_teacher(self, user_id: str, profile_id: str) -> Preference:
        if not self.teacher_profiles:
            raise ProviderError("当前服务未配置教师画像存储")
        profile = self.teacher_profiles.get(user_id, profile_id)
        return self.preferences.update(
            user_id,
            PreferenceUpdate(
                mode=RewriteMode.filter,
                style_prompt=teacher_style_prompt(profile),
                teacher_profile_id=profile.profile_id,
                teacher_profile_name=profile.name,
            ),
        )
