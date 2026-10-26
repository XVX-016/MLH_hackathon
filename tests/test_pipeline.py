"""Tests for asynchronous, validated chunk extraction."""

from __future__ import annotations

import asyncio

from videograph.chunk import TranscriptChunk
from videograph.extract import extract_chunk, extract_chunks
from videograph.schemas import TranscriptSegment


def _chunk(chunk_id: int = 0) -> TranscriptChunk:
    segment = TranscriptSegment(id=chunk_id, start=float(chunk_id * 10), end=float(chunk_id * 10 + 5), text="Transformers use attention.")
    return TranscriptChunk(chunk_id=chunk_id, start=segment.start, end=segment.end, text=segment.text, segments=[segment])


class MockClient:
    def __init__(self, replies: list[str]):
        self.replies = replies
        self.prompts: list[str] = []

    async def complete(self, prompt: str, model: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0)


VALID_EXTRACTION = '{"entities":[{"name":"Transformer","type":"Technology","aliases":[]}],"relations":[]}'


def test_extract_chunk_retries_after_malformed_json(tmp_path) -> None:
    client = MockClient(["not json", VALID_EXTRACTION])

    result = asyncio.run(extract_chunk(_chunk(), client, cache_dir=tmp_path))

    assert result is not None
    assert result.entities[0].name == "Transformer"
    assert len(client.prompts) == 2
    assert "validation error" in client.prompts[1].lower()


def test_extract_chunk_skips_after_retry_failure(tmp_path, caplog) -> None:
    client = MockClient(["{", "still not json"])

    result = asyncio.run(extract_chunk(_chunk(), client, cache_dir=tmp_path))

    assert result is None
    assert len(client.prompts) == 2
    assert "Skipping chunk" in caplog.text


def test_extract_chunks_uses_cached_valid_output(tmp_path) -> None:
    first_client = MockClient([VALID_EXTRACTION])
    chunks = [_chunk()]
    assert len(asyncio.run(extract_chunks(chunks, client=first_client, cache_dir=tmp_path))) == 1

    cached_client = MockClient([])
    assert len(asyncio.run(extract_chunks(chunks, client=cached_client, cache_dir=tmp_path))) == 1
    assert cached_client.prompts == []


def test_parse_vtt_or_srt_malformed_raises_error() -> None:
    import pytest
    from videograph.transcribe import parse_vtt_or_srt

    with pytest.raises(ValueError, match="empty"):
        parse_vtt_or_srt("")

    with pytest.raises(ValueError, match="Malformed subtitle format"):
        parse_vtt_or_srt("This is just plain text without any cues or timestamps.")


# ── Flashcard extraction tests ────────────────────────────────────────────────

VALID_FLASHCARDS = (
    '{"flashcards":[{"id":0,"question":"What does attention do?",'
    '"answer":"It connects tokens.","key_quote":"attention connects tokens",'
    '"start_sec":0.0,"end_sec":5.0}]}'
)


def test_generate_flashcards_returns_schema_compliant_cards() -> None:
    from videograph.extract import FlashcardsOutput, generate_flashcards
    from videograph.schemas import Flashcard
    import json

    calls: list[str] = []

    def fake_llm(prompt, schema, model):
        calls.append(prompt)
        return FlashcardsOutput.model_validate(json.loads(VALID_FLASHCARDS))

    cards = generate_flashcards([_chunk(0), _chunk(1)], llm_call=fake_llm)

    assert len(cards) == 2  # one per chunk
    assert all(isinstance(c, Flashcard) for c in cards)
    # ids must be globally reassigned 0, 1, ...
    assert [c.id for c in cards] == [0, 1]
    assert cards[0].question == "What does attention do?"
    assert len(calls) == 2


def test_generate_flashcards_skips_chunk_on_llm_failure(caplog) -> None:
    from videograph.extract import generate_flashcards
    import json

    call_count = 0

    def flaky_llm(prompt, schema, model):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("LLM returned garbage")
        from videograph.extract import FlashcardsOutput
        return FlashcardsOutput.model_validate(json.loads(VALID_FLASHCARDS))

    cards = generate_flashcards([_chunk(0), _chunk(1)], llm_call=flaky_llm)

    assert len(cards) == 1  # first chunk skipped, second succeeds
    assert "Skipping flashcard extraction" in caplog.text
    assert cards[0].id == 0  # global id reassigned


def test_generate_flashcards_empty_chunks_returns_empty() -> None:
    from videograph.extract import generate_flashcards

    assert generate_flashcards([]) == []


# ── YouTube metadata tests ────────────────────────────────────────────────────

def test_fetch_youtube_metadata_parses_ytdlp_output(monkeypatch) -> None:
    import subprocess
    from videograph.ingest import fetch_youtube_metadata

    fake_stdout = "Attention Is All You Need\t1234\tGoogle Brain\thttps://img.youtube.com/thumb.jpg\n"

    class FakeResult:
        returncode = 0
        stdout = fake_stdout
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/yt-dlp")

    meta = fetch_youtube_metadata("https://www.youtube.com/watch?v=abc123")

    assert meta["title"] == "Attention Is All You Need"
    assert meta["duration"] == 1234.0
    assert meta["channel"] == "Google Brain"
    assert "thumb" in meta["thumbnail"]


def test_fetch_youtube_metadata_raises_on_private_video(monkeypatch) -> None:
    import subprocess, pytest
    from videograph.ingest import fetch_youtube_metadata

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "ERROR: This video is private."

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/yt-dlp")

    with pytest.raises(ValueError, match="unavailable or private"):
        fetch_youtube_metadata("https://www.youtube.com/watch?v=private123")


def test_download_youtube_audio_rejects_long_video(monkeypatch) -> None:
    import pytest
    from videograph.ingest import download_youtube_audio

    # Patch fetch_youtube_metadata to return a 15-minute video
    monkeypatch.setattr(
        "videograph.ingest.fetch_youtube_metadata",
        lambda url: {"title": "Long Video", "duration": 900.0, "channel": "", "thumbnail": "", "url": url},
    )

    with pytest.raises(ValueError, match="exceeds maximum"):
        download_youtube_audio("https://www.youtube.com/watch?v=toolong", output_dir="/tmp")
