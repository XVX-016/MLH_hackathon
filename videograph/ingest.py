"""Video and audio ingestion module for videograph.

Converts input audio/video to 16kHz mono WAV using ffmpeg.
Rejects media files whose duration exceeds 10 minutes (600 seconds).
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple
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


def _get_ytdlp_cmd() -> List[str]:
    """Return command list for invoking yt-dlp across system, Scripts, or python module."""
    sys_ytdlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if sys_ytdlp:
        return [sys_ytdlp]

    candidates = [
        Path(sys.executable).parent / "Scripts" / "yt-dlp.exe",
        Path(sys.executable).parent / "yt-dlp.exe",
        Path(os.environ.get("APPDATA", "")) / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts" / "yt-dlp.exe",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts" / "yt-dlp.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate)]

    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        pass

    raise RuntimeError(
        "yt-dlp is required for YouTube URL support. "
        "Install it with: pip install yt-dlp"
    )


def _get_ytdlp_binary() -> str:
    """Return yt-dlp executable, preferring system install."""
    return _get_ytdlp_cmd()[0]


def fetch_youtube_metadata(url: str) -> dict:
    """Fetch video metadata from a YouTube URL without downloading media.

    Uses yt-dlp in flat/info-only mode. No video or audio bytes are downloaded.

    Args:
        url: A YouTube video URL (e.g. https://www.youtube.com/watch?v=...).

    Returns:
        dict with keys: title, duration (float seconds), channel, thumbnail, url.

    Raises:
        ValueError: If the URL is not a valid or accessible YouTube video.
        RuntimeError: If yt-dlp is not installed or exits unexpectedly.
    """
    cmd = [
        *_get_ytdlp_cmd(),
        "--no-playlist",
        "--no-update",
        "--skip-download",
        "--print", "%(title)s\t%(duration)s\t%(channel)s\t%(thumbnail)s",
        url,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        stderr_lower = result.stderr.lower()
        if "private" in stderr_lower or "unavailable" in stderr_lower or "not found" in stderr_lower:
            raise ValueError(f"YouTube video is unavailable or private: {url}")
        raise ValueError(
            f"Could not fetch metadata for URL '{url}'. "
            f"Ensure the URL is a valid public YouTube video.\nDetails: {result.stderr.strip()}"
        )

    parts = result.stdout.strip().split("\t")
    if len(parts) < 2:
        raise ValueError(f"Unexpected yt-dlp output for URL '{url}': {result.stdout.strip()!r}")

    try:
        duration = float(parts[1]) if parts[1] not in ("", "NA", "None") else 0.0
    except ValueError:
        duration = 0.0

    return {
        "title": parts[0] if parts[0] else "Untitled",
        "duration": duration,
        "channel": parts[2] if len(parts) > 2 else "",
        "thumbnail": parts[3] if len(parts) > 3 else "",
        "url": url,
    }


def download_youtube_subtitles(
    url: str,
    output_dir: str,
    lang: str = "en",
    max_duration_sec: float = MAX_VIDEO_DURATION_SEC,
) -> Optional[str]:
    """Download auto-generated or manual subtitles from a YouTube video.

    This is the preferred fast path for YouTube URL processing — it avoids
    downloading any audio/video bytes and is immune to 403 errors.

    Args:
        url: A YouTube video URL.
        output_dir: Directory in which to save the subtitle file.
        lang: Subtitle language code (default: ``en``).
        max_duration_sec: Maximum allowed duration in seconds.

    Returns:
        Absolute path to the downloaded VTT/SRT file, or ``None`` if no
        subtitles are available for the requested language.

    Raises:
        ValueError: If the video exceeds the duration limit.
    """
    meta = fetch_youtube_metadata(url)
    if meta["duration"] > max_duration_sec:
        raise ValueError(
            f"YouTube video duration ({meta['duration']:.0f}s) exceeds maximum "
            f"allowed {max_duration_sec:.0f}s (10 minutes)."
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = "".join(c if c.isalnum() or c in " _-" else "_" for c in meta["title"])[:60].strip()
    template = str(out_dir / f"{safe_stem}.%(ext)s")

    cmd = [
        *_get_ytdlp_cmd(),
        "--no-playlist",
        "--no-update",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", lang,
        "--sub-format", "vtt/srt/best",
        "--skip-download",
        "-o", template,
        url,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Look for the downloaded subtitle file
    for ext in ("vtt", "srt"):
        candidate = out_dir / f"{safe_stem}.{lang}.{ext}"
        if candidate.is_file():
            return str(candidate)

    # yt-dlp may have used a slightly different naming pattern
    for ext in ("vtt", "srt"):
        matches = list(out_dir.glob(f"{safe_stem}*.{ext}"))
        if matches:
            return str(matches[0])

    return None


def download_youtube_audio(
    url: str,
    output_dir: str,
    max_duration_sec: float = MAX_VIDEO_DURATION_SEC,
) -> str:
    """Download audio from a YouTube URL and normalise to 16kHz mono WAV.

    The video metadata is fetched first to enforce the duration limit without
    downloading the full media. yt-dlp then extracts the best available audio
    stream. The resulting file is converted to 16kHz mono WAV via ingest_media().

    Args:
        url: A YouTube video URL.
        output_dir: Directory in which to save the downloaded and converted file.
        max_duration_sec: Maximum allowed duration in seconds (default 600s / 10 min).

    Returns:
        Absolute path to the normalised 16kHz mono WAV file.

    Raises:
        ValueError: If the video is unavailable, private, or exceeds the duration limit.
        RuntimeError: If yt-dlp or ffmpeg fails.
    """
    meta = fetch_youtube_metadata(url)
    if meta["duration"] > max_duration_sec:
        raise ValueError(
            f"YouTube video duration ({meta['duration']:.0f}s) exceeds maximum "
            f"allowed {max_duration_sec:.0f}s (10 minutes)."
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use a sanitised title as the stem; yt-dlp adds its own extension
    safe_stem = "".join(c if c.isalnum() or c in " _-" else "_" for c in meta["title"])[:60].strip()
    template = str(out_dir / f"{safe_stem}.%(ext)s")

    cmd = [
        *_get_ytdlp_cmd(),
        "--no-playlist",
        "--no-update",
        "--extractor-args", "youtube:player_client=android,web",
        "-f", "bestaudio/best",
        "-o", template,
        url,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp audio download failed: {result.stderr.strip()}")

    # Locate the downloaded file (yt-dlp chooses the extension)
    downloaded = sorted(out_dir.glob(f"{safe_stem}.*"))
    if not downloaded:
        raise RuntimeError(f"yt-dlp ran successfully but no output file was found in {output_dir}.")

    raw_path = str(downloaded[-1])
    wav_path = str(out_dir / f"{safe_stem}_16k_mono.wav")
    return ingest_media(raw_path, output_wav_path=wav_path, max_duration_sec=max_duration_sec)

