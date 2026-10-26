"""Tests for ingest.py and transcribe.py."""

import os
import wave
import struct
import pytest
from pathlib import Path
from unittest.mock import patch

from videograph.ingest import ingest_media, get_media_duration, MAX_VIDEO_DURATION_SEC
from videograph.transcribe import (
    transcribe,
    compute_file_hash,
    register_hosted_client,
    HostedTranscriptionClient,
)
from videograph.schemas import Segment


def create_dummy_wav(path: str, duration_sec: float = 2.0, sample_rate: int = 16000):
    """Helper to generate a clean synthetic WAV file with specific duration."""
    n_frames = int(duration_sec * sample_rate)
    with wave.open(path, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        # 440 Hz sine-like values
        data = [int(1000 * (i % 20)) for i in range(n_frames)]
        packed = struct.pack(f"<{len(data)}h", *data)
        wav.writeframes(packed)


def test_ingest_converts_to_16k_mono_wav(tmp_path):
    src_wav = str(tmp_path / "sample_src.wav")
    create_dummy_wav(src_wav, duration_sec=1.5, sample_rate=44100)

    out_wav = str(tmp_path / "sample_converted.wav")
    result_path = ingest_media(src_wav, output_wav_path=out_wav)
    assert os.path.exists(result_path)

    # Check WAV properties
    with wave.open(result_path, "r") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000


def test_ingest_rejects_files_over_10_minutes(tmp_path):
    src_wav = str(tmp_path / "sample_long.wav")
    create_dummy_wav(src_wav, duration_sec=1.0)

    # Mock get_media_duration to simulate file exceeding 10 minutes (601 seconds)
    with patch("videograph.ingest.get_media_duration", return_value=605.0):
        with pytest.raises(ValueError) as exc:
            ingest_media(src_wav)
        assert "exceeds maximum allowed 600.0s (10 minutes)" in str(exc.value)


def test_transcribe_fake_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_BACKEND", "fake")
    sample_file = str(tmp_path / "test_fake.wav")
    create_dummy_wav(sample_file, duration_sec=2.0)

    segments = transcribe(sample_file)
    assert len(segments) == 2
    assert segments[0].start == 0.0
    assert "videograph" in segments[0].text
    assert isinstance(segments[0], Segment)


def test_transcribe_caching_by_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_BACKEND", "fake")
    sample_file = str(tmp_path / "test_cache.wav")
    create_dummy_wav(sample_file, duration_sec=1.0)

    file_hash = compute_file_hash(sample_file)
    seg1 = transcribe(sample_file)

    # Even if we change backend to invalid string, cached result is returned directly
    monkeypatch.setenv("TRANSCRIBE_BACKEND", "invalid_backend")
    seg2 = transcribe(sample_file)

    assert seg1 == seg2
    assert len(seg2) == 2


def test_transcribe_custom_hosted_client_interface(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_BACKEND", "api")
    sample_file = str(tmp_path / "test_api_client.wav")
    create_dummy_wav(sample_file, duration_sec=3.5)

    class CustomMockAPIClient:
        def transcribe(self, file_path: str):
            return [
                Segment(id=0, start=0.0, end=3.0, text="Mock hosted API transcription result")
            ]

    register_hosted_client(CustomMockAPIClient())
    segments = transcribe(sample_file)
    assert len(segments) == 1
    assert segments[0].text == "Mock hosted API transcription result"
