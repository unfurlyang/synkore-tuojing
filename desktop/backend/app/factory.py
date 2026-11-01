from __future__ import annotations

from app.config import Settings
from app.pipeline import VoicePipeline
from app.preferences import PreferenceStore
from app.providers.base import ProviderError
from app.providers.rules import NoTTS, RuleRewriter
from app.providers.mimo import MimoASR, MimoRewriter, MimoTeacherProfiler, MimoTTS, MimoVoiceCloneTTS
from app.providers.openai_compatible import OpenAICompatibleASR, OpenAICompatibleRewriter, OpenAICompatibleTeacherProfiler, OpenAICompatibleTTS
from app.teachers import TeacherStore
from app.speech_accuracy import VerifiedTTS


def build_pipeline(settings: Settings) -> VoicePipeline:
    if settings.asr_provider == "mimo":
        asr = MimoASR(
            settings.asr_base_url,
            settings.asr_api_key,
            settings.asr_model,
            settings.asr_language,
            settings.llm_timeout_seconds,
        )
    elif settings.asr_provider == "openai":
        asr = OpenAICompatibleASR(settings.asr_base_url, settings.asr_api_key, settings.asr_model)
    else:
        raise ProviderError(f"不支持的 ASR_PROVIDER: {settings.asr_provider}")

    if settings.rewrite_provider == "mimo":
        rewriter = MimoRewriter(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds)
    elif settings.rewrite_provider == "openai":
        rewriter = OpenAICompatibleRewriter(
            settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds
        )
    elif settings.rewrite_provider == "rules":
        rewriter = RuleRewriter()
    else:
        raise ProviderError(f"不支持的 REWRITE_PROVIDER: {settings.rewrite_provider}")

    if settings.rewrite_provider == "mimo":
        teacher_profiler = MimoTeacherProfiler(
            settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds
        )
    elif settings.rewrite_provider == "openai":
        teacher_profiler = OpenAICompatibleTeacherProfiler(
            settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds
        )
    else:
        teacher_profiler = None

    if settings.tts_provider == "mimo":
        tts = MimoTTS(settings.tts_base_url, settings.tts_api_key, settings.tts_model, settings.tts_voice, settings.llm_timeout_seconds)
    elif settings.tts_provider == "openai":
        tts = OpenAICompatibleTTS(
            settings.tts_base_url, settings.tts_api_key, settings.tts_model, settings.tts_voice
        )
    elif settings.tts_provider == "none":
        tts = NoTTS()
    else:
        raise ProviderError(f"不支持的 TTS_PROVIDER: {settings.tts_provider}")

    if settings.tts_provider != 'none':tts=VerifiedTTS(tts,asr)
    voice_clone=VerifiedTTS(MimoVoiceCloneTTS(settings.tts_base_url,settings.tts_api_key,settings.llm_timeout_seconds),asr) if settings.tts_provider=='mimo' else None
    return VoicePipeline(
        asr=asr,
        rewriter=rewriter,
        tts=tts,
        preferences=PreferenceStore(settings.data_dir / "preferences.json"),
        audio_dir=settings.data_dir / "audio",
        teacher_profiles=TeacherStore(settings.data_dir / "teachers.json"),
        teacher_profiler=teacher_profiler,
        voice_dir=settings.data_dir / "voice_samples",
        voice_clone=voice_clone,
    )
