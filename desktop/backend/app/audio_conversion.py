from __future__ import annotations

import asyncio
import tempfile
import uuid
import os
from pathlib import Path

import imageio_ffmpeg

from app.providers.base import ProviderError


async def convert_m4a_clip_to_wav(content: bytes, start_seconds: float, duration_seconds: float) -> bytes:
    """Decode an M4A clip to 16 kHz mono WAV; no speech model runs locally."""
    temp_dir = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))) / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    input_path = temp_dir / f"{uuid.uuid4().hex}.m4a"
    output_path = temp_dir / f"{uuid.uuid4().hex}.wav"
    input_path.write_bytes(content)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-y",
        str(output_path),
    ]
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except OSError as exc:
            raise ProviderError(f"音频转换工具启动失败: {exc}") from exc
        if process.returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 78:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise ProviderError(
                "M4A 解码失败或所选片段没有音频，请检查文件和起始位置"
                + (f": {detail[-500:]}" if detail else "")
            )
        return output_path.read_bytes()
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


async def convert_audio_to_wav_chunks(
    content: bytes,
    extension: str,
    start_seconds: float = 0,
    duration_seconds: float | None = None,
    chunk_seconds: int = 90,
    max_chunks: int = 48,
) -> list[bytes]:
    """Decode any supported upload into ordered ASR-sized WAV chunks.

    This is format conversion only; no local speech model is used.
    """
    temp_root = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))) / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as directory:
        temp_dir = Path(directory)
        input_path = temp_dir / f"input{extension}"
        input_path.write_bytes(content)
        output_pattern = temp_dir / "chunk-%03d.wav"
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start_seconds:.3f}",
        ]
        if duration_seconds is not None:
            command.extend(["-t", f"{duration_seconds:.3f}"])
        command.extend(
            [
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-f",
                "segment",
                "-segment_time",
                str(chunk_seconds),
                "-reset_timestamps",
                "1",
                "-y",
                str(output_pattern),
            ]
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except OSError as exc:
            raise ProviderError(f"音频转换工具启动失败: {exc}") from exc
        paths = sorted(temp_dir.glob("chunk-*.wav"))
        if process.returncode != 0 or not paths:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise ProviderError("课程音频解码失败或所选范围没有音频" + (f": {detail[-500:]}" if detail else ""))
        if len(paths) > max_chunks:
            raise ProviderError(f"课程超过当前 {max_chunks} 个分段上限，请缩短课程或提高分段时长")
        chunks = [path.read_bytes() for path in paths if path.stat().st_size > 78]
        if not chunks:
            raise ProviderError("课程音频没有解码出有效声音")
        return chunks
