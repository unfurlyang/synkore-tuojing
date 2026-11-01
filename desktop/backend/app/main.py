from __future__ import annotations

import json
import re
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.audio_conversion import convert_audio_to_wav_chunks, convert_m4a_clip_to_wav
from app.config import Settings
from app.factory import build_pipeline
from app.pipeline import VoicePipeline
from app.preferences import PreferenceNotFound
from app.providers.base import ProviderError
from app.schemas import InputMode, Preference, PreferenceUpdate, ProcessResponse, TeacherListResponse, TeacherProfile, TeacherTextRequest, TextProcessRequest
from app.teachers import TeacherNotFound
from app.companion_voice import CompanionVoice, CompanionSpeechRequest

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a"}
AUDIO_MEDIA_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}


async def ndjson(events):
    async for event in events:
        yield (json.dumps(event, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def stream_response(events) -> StreamingResponse:
    return StreamingResponse(
        ndjson(events),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def create_app(settings: Settings | None = None, pipeline: VoicePipeline | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    pipeline = pipeline or build_pipeline(settings)
    app = FastAPI(title="synkore 课程服务", version="4.0.0")
    companion_voice = CompanionVoice(settings, pipeline.audio_dir)
    from app.library import install_library
    install_library(app, pipeline, settings)
    local_token = os.environ.get("LOCAL_APP_TOKEN", "")
    ui_dir = Path(os.environ.get("COURSE_WEB_DIR", str(Path(__file__).parent / "static")))

    @app.middleware("http")
    async def local_access(request, call_next):
        if local_token and request.url.path.startswith('/v1/') and request.url.path != '/v1/health':
            if not secrets.compare_digest(request.headers.get('X-App-Token', ''), local_token):
                return JSONResponse(status_code=401, content={"detail": "请从synkore App 打开此功能"})
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    if (ui_dir / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=ui_dir / 'assets'), name='assets')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_request, exc: ProviderError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=502, content={"code": "provider_error", "detail": str(exc)})

    @app.get("/", include_in_schema=False)
    async def root():
        html = (ui_dir / 'index.html').read_text(encoding='utf-8')
        return HTMLResponse(html.replace('__LOCAL_APP_TOKEN__', local_token))

    @app.get("/v1/health")
    async def health():
        asr_ready = getattr(pipeline.asr, "configured", pipeline.asr.name in {"mimo", "openai"})
        rewrite_ready = getattr(pipeline.rewriter, "configured", True)
        tts_ready = getattr(pipeline.tts, "configured", pipeline.tts.name in {"mimo", "openai", "none"})
        return {
            "status": "ok",
            "max_upload_bytes": settings.max_upload_bytes,
            "ready_for_audio": asr_ready and rewrite_ready and tts_ready,
            "providers": pipeline.provider_names,
            "capabilities": {
                "asr_configured": asr_ready,
                "rewrite_configured": rewrite_ready,
                "tts_configured": tts_ready,
                "streaming_rewrite": hasattr(pipeline.rewriter, "rewrite_stream"),
                "streaming_tts": hasattr(pipeline.tts, "synthesize_stream"),
                "transcript_proofreading": hasattr(pipeline.rewriter, "proofread"),
            },
            "note": "ready_for_audio 只表示云端适配器和密钥已配置，不代表外部服务已完成真实调用验收",
        }

    @app.get("/v1/preferences/{user_id}", response_model=Preference)
    async def get_preference(user_id: str):
        return pipeline.preferences.get(user_id)

    @app.put("/v1/preferences/{user_id}", response_model=Preference)
    async def update_preference(user_id: str, update: PreferenceUpdate):
        return pipeline.preferences.update(user_id, update)

    @app.post("/v1/preferences/{user_id}/undo", response_model=Preference)
    async def undo_preference(user_id: str):
        try:
            return pipeline.preferences.undo(user_id)
        except PreferenceNotFound as exc:
            raise HTTPException(status_code=404, detail="没有可撤销的偏好修改") from exc

    @app.post("/v1/process/text", response_model=ProcessResponse)
    async def process_text(request: TextProcessRequest):
        preference = pipeline.preferences.get(request.user_id)
        if request.preference_version and request.preference_version != preference.version:
            raise HTTPException(
                status_code=409,
                detail=f"偏好已更新，客户端版本 {request.preference_version}，当前版本 {preference.version}",
            )
        return await pipeline.process_text(request.user_id, request.text, request.mode, preference)

    @app.post("/v1/process/text/stream")
    async def process_text_stream(request: TextProcessRequest):
        preference = pipeline.preferences.get(request.user_id)
        if request.preference_version and request.preference_version != preference.version:
            raise HTTPException(status_code=409, detail="偏好已更新，请刷新后重试")
        return stream_response(pipeline.process_text_stream(request.user_id, request.text, request.mode, preference))

    @app.post("/v1/process/audio", response_model=ProcessResponse)
    async def process_audio(
        file: UploadFile = File(...),
        user_id: str = Form(...),
        mode: InputMode = Form(InputMode.playback),
        start_seconds: float = Form(0),
        duration_seconds: float = Form(60),
    ):
        filename = Path(file.filename or "input.wav").name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="支持 wav/mp3/m4a；M4A 会先截取测试片段并转为 WAV")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", user_id):
            raise HTTPException(status_code=422, detail="user_id 只能包含字母、数字、点、下划线和连字符")
        if start_seconds < 0 or start_seconds > 86400:
            raise HTTPException(status_code=422, detail="起始位置必须在 0 到 86400 秒之间")
        if duration_seconds < 1 or duration_seconds > 120:
            raise HTTPException(status_code=422, detail="测试片段时长必须在 1 到 120 秒之间")
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"音频超过 {settings.max_upload_bytes // 1024 // 1024} MB 限制")
        if not content:
            raise HTTPException(status_code=422, detail="音频文件为空")
        conversion_warning = ""
        if extension == ".m4a":
            content = await convert_m4a_clip_to_wav(content, start_seconds, duration_seconds)
            filename = Path(filename).stem + ".wav"
            conversion_warning = (
                f"M4A 已转为 16 kHz 单声道 WAV；本次仅处理第 {start_seconds:g}–{start_seconds + duration_seconds:g} 秒"
            )
        response = await pipeline.process_audio(user_id, content, filename, file.content_type or "", mode)
        if conversion_warning:
            response.warnings.append(conversion_warning)
        return response

    @app.post("/v1/process/audio/stream")
    async def process_audio_stream(
        file: UploadFile = File(...),
        user_id: str = Form(...),
        mode: InputMode = Form(InputMode.realtime),
        start_seconds: float = Form(0),
        duration_seconds: float = Form(60),
    ):
        filename = Path(file.filename or "input.wav").name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="流式处理支持 wav/mp3/m4a")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", user_id):
            raise HTTPException(status_code=422, detail="user_id 格式无效")
        if start_seconds < 0 or start_seconds > 86400:
            raise HTTPException(status_code=422, detail="起始位置必须在 0 到 86400 秒之间")
        if duration_seconds < 1 or duration_seconds > 120:
            raise HTTPException(status_code=422, detail="测试片段时长必须在 1 到 120 秒之间")
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"音频超过 {settings.max_upload_bytes // 1024 // 1024} MB 限制")
        if not content:
            raise HTTPException(status_code=422, detail="音频文件为空")
        if extension == ".m4a":
            content = await convert_m4a_clip_to_wav(content, start_seconds, duration_seconds)
            filename = Path(filename).stem + ".wav"
        return stream_response(
            pipeline.process_audio_stream(user_id, content, filename, file.content_type or "", mode)
        )

    @app.get("/v1/teachers", response_model=TeacherListResponse)
    async def list_teachers(user_id: str):
        if not pipeline.teacher_profiles:
            return TeacherListResponse(items=[])
        return TeacherListResponse(items=pipeline.teacher_profiles.list(user_id))

    @app.post("/v1/teachers/from-text", response_model=TeacherProfile)
    async def distill_teacher_text(request: TeacherTextRequest):
        return await pipeline.distill_teacher_text(
            request.user_id, request.teacher_name, request.transcript, "text-input"
        )

    @app.post("/v1/teachers/distill", response_model=TeacherProfile)
    async def distill_teacher(
        file: UploadFile = File(...),
        user_id: str = Form(...),
        teacher_name: str = Form(...),
        start_seconds: float = Form(0),
        duration_seconds: float = Form(120),
        full_course: bool = Form(False),
        voice_consent: bool = Form(False),
    ):
        filename = Path(file.filename or "teacher.wav").name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="教师录入支持 wav/mp3/m4a")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", user_id):
            raise HTTPException(status_code=422, detail="user_id 格式无效")
        teacher_name = teacher_name.strip()
        if not 1 <= len(teacher_name) <= 80:
            raise HTTPException(status_code=422, detail="教师画像名称必须为 1–80 个字符")
        if start_seconds < 0 or start_seconds > 86400:
            raise HTTPException(status_code=422, detail="起始位置必须在 0 到 86400 秒之间")
        if not full_course and not 10 <= duration_seconds <= 120:
            raise HTTPException(status_code=422, detail="短样本时长必须在 10 到 120 秒之间")
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"音频超过 {settings.max_upload_bytes // 1024 // 1024} MB 限制")
        if not content:
            raise HTTPException(status_code=422, detail="音频文件为空")
        chunks = await convert_audio_to_wav_chunks(
            content,
            extension,
            start_seconds=start_seconds,
            duration_seconds=None if full_course else duration_seconds,
        )
        return await pipeline.distill_teacher_audio(user_id, teacher_name, chunks, filename, voice_consent)

    @app.post("/v1/postprocess/course/stream")
    async def postprocess_course(
        file: UploadFile = File(...),
        user_id: str = Form(...),
        profile_id: str = Form(...),
        use_teacher_voice: bool = Form(False),
        voice_consent: bool = Form(False),
        full_course: bool = Form(True),
        start_seconds: float = Form(0),
        duration_seconds: float = Form(120),
    ):
        filename = Path(file.filename or "course.m4a").name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="课后转化支持 wav/mp3/m4a")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", user_id):
            raise HTTPException(status_code=422, detail="user_id 格式无效")
        if use_teacher_voice and not voice_consent:
            raise HTTPException(status_code=403, detail="使用教师音色前必须确认已获得教师授权")
        if not pipeline.teacher_profiles:
            raise HTTPException(status_code=404, detail="教师画像库不可用")
        try:
            pipeline.teacher_profiles.get(user_id, profile_id)
        except TeacherNotFound as exc:
            raise HTTPException(status_code=404, detail="教师画像不存在或不属于当前用户") from exc
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"音频超过 {settings.max_upload_bytes // 1024 // 1024} MB 限制")
        if not content:
            raise HTTPException(status_code=422, detail="音频文件为空")
        chunks = await convert_audio_to_wav_chunks(
            content, extension, start_seconds=start_seconds,
            duration_seconds=None if full_course else duration_seconds,
        )
        return stream_response(
            pipeline.process_post_course_stream(user_id, profile_id, chunks, use_teacher_voice)
        )

    @app.put("/v1/preferences/{user_id}/teacher/{profile_id}", response_model=Preference)
    async def select_teacher(user_id: str, profile_id: str):
        try:
            return pipeline.select_teacher(user_id, profile_id)
        except TeacherNotFound as exc:
            raise HTTPException(status_code=404, detail="教师画像不存在或不属于当前用户") from exc

    @app.post("/v1/companion/speech")
    async def companion_speech(request: CompanionSpeechRequest):
        return {"audio_url": await companion_voice.speak(request), "pack": request.pack, "text": request.text, "verified": True}

    @app.get("/v1/audio/{filename}")
    async def get_audio(filename: str):
        if not re.fullmatch(r"[a-f0-9]{32}\.(?:wav|mp3|ogg)", filename):
            raise HTTPException(status_code=404, detail="音频不存在")
        path = pipeline.audio_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="音频不存在")
        return FileResponse(path, media_type=AUDIO_MEDIA_TYPES.get(path.suffix, "application/octet-stream"))

    return app


app = create_app()
