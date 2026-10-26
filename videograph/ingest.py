"""Video ingestion module.

Handles local video files, URL downloads via yt-dlp, and audio extraction via ffmpeg.
"""

from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import imageio_ffmpeg


def get_ffmpeg_binary() -> str:
    """Return available ffmpeg executable path."""
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def get_video_duration(video_path: str) -> float:
    """Estimate or extract video duration in seconds."""
    ffmpeg_exe = get_ffmpeg_binary()
    try:
        # Run quick ffmpeg probe
        cmd = [ffmpeg_exe, "-i", video_path]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Parse Duration: 00:01:23.45 from stderr
        for line in proc.stderr.splitlines():
            if "Duration:" in line:
                part = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = part.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


def extract_audio(video_path: str, output_audio_path: Optional[str] = None) -> str:
    """Extract 16kHz mono WAV or MP3 audio from a video file using ffmpeg.
    
    Args:
        video_path: Path to input video file.
        output_audio_path: Optional path for generated audio file.
        
    Returns:
        Path to generated audio file.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Input video file not found: {video_path}")

    if not output_audio_path:
        stem = Path(video_path).stem
        output_audio_path = str(Path(video_path).parent / f"{stem}_audio.mp3")

    ffmpeg_exe = get_ffmpeg_binary()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "16000",
        "-ac", "1",
        output_audio_path,
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

    return output_audio_path


def download_video_or_audio(url: str, output_dir: str) -> Tuple[str, str]:
    """Download video or audio stream from YouTube/web using yt-dlp.
    
    Returns:
        (downloaded_file_path, title)
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "ba/b",  # Best audio or best video
        "-o", out_template,
        "--print", "after_move:filepath",
        "--print", "title",
        url,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {proc.stderr}")

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) >= 2:
        file_path = lines[0]
        title = lines[1]
    elif len(lines) == 1:
        file_path = lines[0]
        title = Path(file_path).stem
    else:
        file_path = str(list(Path(output_dir).glob("*.*"))[-1])
        title = Path(file_path).stem

    return file_path, title
