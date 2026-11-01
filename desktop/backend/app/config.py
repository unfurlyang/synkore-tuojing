from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(Path(os.getenv("COURSE_ENV_FILE", str(ROOT_DIR / ".env"))))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    asr_provider: str
    asr_base_url: str
    asr_api_key: str
    asr_model: str
    asr_language: str
    rewrite_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: int
    tts_provider: str
    tts_base_url: str
    tts_api_key: str
    tts_model: str
    tts_voice: str
    max_upload_bytes: int
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir_setting = Path(_env("DATA_DIR", "data"))
        data_dir = data_dir_setting if data_dir_setting.is_absolute() else ROOT_DIR / data_dir_setting
        mimo_url = _env("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
        mimo_key = _env("MIMO_API_KEY")
        asr_provider = _env("ASR_PROVIDER", "mimo").lower()
        rewrite_provider = _env("REWRITE_PROVIDER", "mimo").lower()
        tts_provider = _env("TTS_PROVIDER", "mimo").lower()

        if rewrite_provider == "mimo":
            llm_base_url = mimo_url
            llm_key = mimo_key
            llm_model = _env("MIMO_LLM_MODEL", "mimo-v2.6-flash")
        else:
            llm_base_url = _env("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            llm_key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
            llm_model = _env("LLM_MODEL", "gpt-4o-mini")

        return cls(
            root_dir=ROOT_DIR,
            data_dir=data_dir,
            asr_provider=asr_provider,
            asr_base_url=mimo_url if asr_provider == "mimo" else _env("ASR_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            asr_api_key=mimo_key if asr_provider == "mimo" else _env("ASR_API_KEY") or _env("OPENAI_API_KEY"),
            asr_model=_env("MIMO_ASR_MODEL", "mimo-v2.5-asr") if asr_provider == "mimo" else _env("ASR_MODEL", "gpt-4o-mini-transcribe"),
            asr_language=_env("ASR_LANGUAGE", "zh"),
            rewrite_provider=rewrite_provider,
            llm_base_url=llm_base_url,
            llm_api_key=llm_key,
            llm_model=llm_model,
            llm_timeout_seconds=_int_env("MIMO_TIMEOUT_SECONDS", _int_env("LLM_TIMEOUT_SECONDS", 60)),
            tts_provider=tts_provider,
            tts_base_url=mimo_url if tts_provider == "mimo" else _env("TTS_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            tts_api_key=mimo_key if tts_provider == "mimo" else _env("TTS_API_KEY") or _env("OPENAI_API_KEY"),
            tts_model=_env("MIMO_TTS_MODEL", "mimo-v2.5-tts") if tts_provider == "mimo" else _env("TTS_MODEL", "gpt-4o-mini-tts"),
            tts_voice=_env("MIMO_TTS_VOICE", "mimo_default") if tts_provider == "mimo" else _env("TTS_VOICE", "alloy"),
            max_upload_bytes=_int_env("MAX_UPLOAD_MB", 64) * 1024 * 1024,
            cors_origins=tuple(
                item.strip()
                for item in _env(
                    "CORS_ORIGINS",
                    "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173",
                ).split(",")
                if item.strip()
            ),
        )
