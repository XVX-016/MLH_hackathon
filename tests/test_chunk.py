"""Tests for timestamp-preserving transcript chunking."""

from videograph.chunk import chunk_transcript
from videograph.schemas import TranscriptSegment


def test_chunking_uses_sixty_second_windows_and_ten_second_overlap() -> None:
    segments = [
        TranscriptSegment(
            id=index,
            start=float(index * 10),
            end=float((index + 1) * 10),
            text=f"Segment {index}",
        )
        for index in range(9)
    ]

    chunks = chunk_transcript(segments)

    assert [(chunk.start, chunk.end) for chunk in chunks] == [
        (0.0, 60.0),
        (50.0, 90.0),
    ]
    assert [segment.id for segment in chunks[1].segments] == [5, 6, 7, 8]


def test_chunking_keeps_a_short_video_in_one_chunk() -> None:
    segments = [
        TranscriptSegment(id=0, start=2.0, end=8.0, text="A short introduction."),
        TranscriptSegment(id=1, start=8.0, end=15.0, text="A short conclusion."),
    ]

    chunks = chunk_transcript(segments)

    assert len(chunks) == 1
    assert chunks[0].start == 2.0
    assert chunks[0].end == 15.0
    assert chunks[0].segments == segments


def test_chunking_does_not_split_a_segment_larger_than_the_target() -> None:
    giant_segment = TranscriptSegment(
        id=0,
        start=0.0,
        end=95.0,
        text="One long uninterrupted speaker turn.",
    )
    following_segment = TranscriptSegment(
        id=1,
        start=95.0,
        end=100.0,
        text="A final short turn.",
    )

    chunks = chunk_transcript([giant_segment, following_segment])

    assert [(chunk.start, chunk.end) for chunk in chunks] == [(0.0, 95.0), (95.0, 100.0)]
    assert chunks[0].segments == [giant_segment]
    assert chunks[1].segments == [following_segment]
