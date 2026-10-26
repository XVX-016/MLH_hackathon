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

    # Patch fetch_youtube_metadata to return a video exceeding 15 minutes (905 seconds)
    monkeypatch.setattr(
        "videograph.ingest.fetch_youtube_metadata",
        lambda url: {"title": "Long Video", "duration": 905.0, "channel": "", "thumbnail": "", "url": url},
    )

    with pytest.raises(ValueError, match="exceeds maximum"):
        download_youtube_audio("https://www.youtube.com/watch?v=toolong", output_dir="/tmp")


def test_parse_vtt_with_bom_and_accents() -> None:
    from videograph.transcribe import parse_vtt_or_srt

    # Subtitle with UTF-8 BOM (\ufeff), CRLF (\r\n), styling tags, and French/Spanish accents
    sample_content = (
        "\ufeffWEBVTT\r\n\r\n"
        "1\r\n"
        "00:00:01.000 --> 00:00:04.500\r\n"
        "Bonjour! <c.highlight>C'est un modèle d'attention très sophistiqué.</c>\r\n\r\n"
        "2\r\n"
        "00:00:05,250 --> 00:00:09,750\r\n"
        "El procesamiento del <i>lenguaje natural</i> es increíble.\r\n"
    )

    segments = parse_vtt_or_srt(sample_content)
    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].end == 4.5
    assert segments[0].text == "Bonjour! C'est un modèle d'attention très sophistiqué."
    assert segments[1].start == 5.25
    assert segments[1].end == 9.75
    assert segments[1].text == "El procesamiento del lenguaje natural es increíble."


# --- T1: YouTube fallback chain tests ---

def test_extract_youtube_video_id() -> None:
    from videograph.ingest import extract_youtube_video_id

    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_fallback_chain_success_on_youtube_transcript_api(monkeypatch) -> None:
    from videograph.ingest import ingest_youtube_fallback
    from videograph.schemas import Segment

    monkeypatch.setattr(
        "videograph.ingest.fetch_youtube_metadata",
        lambda url: {"title": "Test Video", "duration": 120.0, "channel": "TestCh", "thumbnail": "", "url": url},
    )
    fake_segments = [
        Segment(id=0, start=0.0, end=4.0, text="Welcome to the video about knowledge graphs."),
        Segment(id=1, start=4.0, end=8.0, text="Knowledge graphs connect entities with typed relations."),
    ]
    monkeypatch.setattr(
        "videograph.ingest.fetch_youtube_transcript_api",
        lambda url, languages=None: fake_segments,
    )

    segments, meta = ingest_youtube_fallback("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert len(segments) == 2
    assert segments[0].text == "Welcome to the video about knowledge graphs."
    assert meta["title"] == "Test Video"


def test_fallback_chain_success_on_ytdlp_subtitles(monkeypatch, tmp_path) -> None:
    from videograph.ingest import ingest_youtube_fallback, NeedsUpload

    monkeypatch.setattr(
        "videograph.ingest.fetch_youtube_metadata",
        lambda url: {"title": "Test Video", "duration": 180.0, "channel": "TestCh", "thumbnail": "", "url": url},
    )
    # Fail step 1
    def mock_fail_api(url, languages=None):
        raise NeedsUpload("No captions from API", reason="disabled")
    monkeypatch.setattr("videograph.ingest.fetch_youtube_transcript_api", mock_fail_api)

    # Succeed step 2 with mock vtt file
    vtt_file = tmp_path / "sub.vtt"
    vtt_file.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\nFallback subtitle text\n", encoding="utf-8")
    monkeypatch.setattr(
        "videograph.ingest.download_youtube_subtitles",
        lambda url, output_dir, **kw: str(vtt_file),
    )

    segments, meta = ingest_youtube_fallback("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert len(segments) == 1
    assert segments[0].text == "Fallback subtitle text"


def test_fallback_chain_raises_needsupload_on_no_captions(monkeypatch) -> None:
    import pytest
    from videograph.ingest import ingest_youtube_fallback, NeedsUpload

    monkeypatch.setattr(
        "videograph.ingest.fetch_youtube_metadata",
        lambda url: {"title": "No Sub Video", "duration": 60.0, "channel": "TestCh", "thumbnail": "", "url": url},
    )
    def mock_fail_api(url, languages=None):
        raise NeedsUpload("Disabled", reason="disabled")
    monkeypatch.setattr("videograph.ingest.fetch_youtube_transcript_api", mock_fail_api)
    monkeypatch.setattr("videograph.ingest.download_youtube_subtitles", lambda *a, **kw: None)

    with pytest.raises(NeedsUpload) as exc:
        ingest_youtube_fallback("https://www.youtube.com/watch?v=nocaptions12")
    assert "upload the file directly or paste its transcript" in str(exc.value)


def test_fallback_chain_raises_needsupload_on_private_or_restricted(monkeypatch) -> None:
    import pytest
    from videograph.ingest import ingest_youtube_fallback, NeedsUpload

    def mock_private_meta(url):
        raise ValueError("This video is private and unavailable without sign in.")
    monkeypatch.setattr("videograph.ingest.fetch_youtube_metadata", mock_private_meta)

    with pytest.raises(NeedsUpload) as exc:
        ingest_youtube_fallback("https://www.youtube.com/watch?v=private12345")
    assert "private, age-restricted, or requires login" in str(exc.value)


# --- T2: Upload limits, media validation, cleanup tests ---

def test_validate_uploaded_media_enforces_extension(tmp_path) -> None:
    import pytest
    from videograph.ingest import validate_uploaded_media

    bad_file = tmp_path / "document.pdf"
    bad_file.write_text("fake pdf data")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        validate_uploaded_media(bad_file)


def test_validate_uploaded_media_enforces_size_limit(tmp_path) -> None:
    import pytest
    from videograph.ingest import validate_uploaded_media

    big_file = tmp_path / "giant.mp4"
    big_file.write_bytes(b"x" * 200)  # 200 bytes

    # Test with custom max_size_bytes of 100 bytes
    with pytest.raises(ValueError, match="exceeds maximum allowed limit"):
        validate_uploaded_media(big_file, max_size_bytes=100)


def test_validate_uploaded_media_enforces_15_min_duration(tmp_path, monkeypatch) -> None:
    import pytest
    from videograph.ingest import validate_uploaded_media

    media_file = tmp_path / "speech.wav"
    media_file.write_bytes(b"dummy wav data")

    # Mock get_media_duration to return 16 minutes (960 seconds)
    monkeypatch.setattr("videograph.ingest.get_media_duration", lambda path: 960.0)

    with pytest.raises(ValueError, match="exceeds maximum allowed 900"):
        validate_uploaded_media(media_file)


def test_cleanup_media_files(tmp_path) -> None:
    from videograph.ingest import cleanup_media_files

    f1 = tmp_path / "temp1.wav"
    f1.write_text("audio1")
    f2 = tmp_path / "temp2.wav"
    f2.write_text("audio2")
    non_existent = tmp_path / "missing.wav"

    assert f1.exists() and f2.exists()
    cleanup_media_files(f1, f2, non_existent, None)
    assert not f1.exists() and not f2.exists()




# ── Rolling auto-caption cleanup ──────────────────────────────────────────────

ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.160 --> 00:00:02.869
Apple has finally unveiled their long

00:00:02.869 --> 00:00:02.879
Apple has finally unveiled their long

00:00:02.879 --> 00:00:05.110
Apple has finally unveiled their long
awaited iPhone with a brand new

00:00:05.110 --> 00:00:05.120
awaited iPhone with a brand new

00:00:05.120 --> 00:00:08.000
awaited iPhone with a brand new
design [Music] and a faster chip.

00:00:08.000 --> 00:00:09.000
[Music]

00:00:09.200 --> 00:00:12.000
Prices start at 799 dollars in the United States starting next Friday.
"""


def test_clean_caption_segments_collapses_rolling_auto_captions() -> None:
    from videograph.transcribe import clean_caption_segments, parse_vtt_or_srt

    raw = parse_vtt_or_srt(ROLLING_VTT)
    cleaned = clean_caption_segments(raw)
    print(f"rolling captions: {len(raw)} segments before, {len(cleaned)} after")

    assert len(raw) == 7
    assert [s.text for s in cleaned] == [
        "Apple has finally unveiled their long awaited iPhone with a brand new design and a faster chip.",
        "Prices start at 799 dollars in the United States starting next Friday.",
    ]
    assert cleaned[0].start == 0.16 and cleaned[0].end == 8.0  # the [Music]-only cue is not speech
    assert [s.id for s in cleaned] == [0, 1]
    assert all("[Music]" not in s.text for s in cleaned)


def test_clean_caption_segments_drops_exact_repeats_and_keeps_clean_input() -> None:
    from videograph.schemas import Segment
    from videograph.transcribe import clean_caption_segments

    clean = [
        Segment(id=0, start=0.0, end=4.0, text="Attention lets a model weigh the most relevant tokens."),
        Segment(id=1, start=4.0, end=8.0, text="Attention lets a model weigh the most relevant tokens."),
        Segment(id=2, start=10.0, end=14.0, text="Multi-head attention repeats this process in parallel."),
    ]
    out = clean_caption_segments(clean)
    assert [s.text for s in out] == [clean[0].text, clean[2].text]
    assert out[0].end == 8.0
