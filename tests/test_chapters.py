"""Tests for validated and fallback chapter generation."""

from videograph.chunk import TranscriptChunk
from videograph.extract import ChaptersOutput, SummaryOutput, generate_chapters_and_summary
from videograph.schemas import Chapter, Entity, KnowledgeGraph, KnowledgeNode


def _chunks() -> list[TranscriptChunk]:
    return [
        TranscriptChunk(chunk_id=0, start=0.0, end=10.0, text="Introduces Transformers."),
        TranscriptChunk(chunk_id=1, start=10.0, end=20.0, text="Explains attention."),
    ]


def test_chapter_starts_are_validated_before_summary() -> None:
    prompts = []

    def fake_llm(prompt, schema, model):
        prompts.append(prompt)
        if schema is ChaptersOutput:
            return ChaptersOutput(chapters=[Chapter(title="Intro", start_sec=0.0, summary="Transformer overview.")])
        return SummaryOutput(summary="A Transformer overview.")

    summary, chapters = generate_chapters_and_summary(
        _chunks(), [[Entity(name="Transformer")], [Entity(name="Attention")]], llm_call=fake_llm
    )

    assert chapters[0].start_sec == 0.0
    assert summary == "A Transformer overview."
    assert "Entities: Transformer" in prompts[0]


def test_invalid_chapter_start_uses_community_fallback() -> None:
    def fake_llm(prompt, schema, model):
        if schema is ChaptersOutput:
            return ChaptersOutput(chapters=[Chapter(title="Invalid", start_sec=3.0, summary="Bad boundary")])
        return SummaryOutput(summary="Fallback summary.")

    graph = KnowledgeGraph(nodes=[KnowledgeNode(id="transformer", label="Transformer")])
    summary, chapters = generate_chapters_and_summary(_chunks(), graph=graph, llm_call=fake_llm)

    assert summary == "Fallback summary."
    assert [chapter.start_sec for chapter in chapters] == [0.0]
    assert chapters[0].title == "Transformer"
