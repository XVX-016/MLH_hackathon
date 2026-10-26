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

