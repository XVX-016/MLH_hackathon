"""Video and audio ingestion module for videograph.

Converts input audio/video to 16kHz mono WAV using ffmpeg.
Rejects media files whose duration exceeds 10 minutes (600 seconds).
"""

from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import imageio_ffmpeg

MAX_VIDEO_DURATION_SEC = 600.0  # 10 minutes max


def get_ffmpeg_binary() -> str:
    """Return available ffmpeg executable path."""
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def get_media_duration(file_path: str) -> float:
    """Extract media duration in seconds using ffmpeg probe output."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ffmpeg_exe = get_ffmpeg_binary()
    cmd = [ffmpeg_exe, "-i", file_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Parse Duration: HH:MM:SS.ss
    for line in proc.stderr.splitlines():
        if "Duration:" in line:
            try:
                part = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = part.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
            except Exception:
                pass
    return 0.0


def ingest_media(
    input_path: str,
    output_wav_path: Optional[str] = None,
    max_duration_sec: float = MAX_VIDEO_DURATION_SEC,
) -> str:
    """Convert video/audio to 16kHz mono WAV and enforce <= 10 min duration.

    Args:
        input_path: Source media file path.
        output_wav_path: Optional destination path for .wav file.
        max_duration_sec: Maximum permitted duration in seconds (default 600.0s).

    Returns:
        Path to converted 16kHz mono WAV file.

    Raises:
        FileNotFoundError: If input_path does not exist.
        ValueError: If file duration exceeds 10 minutes (600s).
        RuntimeError: If ffmpeg fails during conversion.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Media file not found: {input_path}")

    duration = get_media_duration(input_path)
    if duration > max_duration_sec:
        raise ValueError(
            f"File duration ({duration:.1f}s) exceeds maximum allowed {max_duration_sec:.1f}s (10 minutes)."
        )

    if not output_wav_path:
        p = Path(input_path)
        output_wav_path = str(p.parent / f"{p.stem}_16k_mono.wav")

    ffmpeg_exe = get_ffmpeg_binary()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav_path,
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

    return output_wav_path


# Backwards compatibility helpers
extract_audio = ingest_media
get_video_duration = get_media_duration
