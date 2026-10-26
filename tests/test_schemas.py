"""Tests for schemas.py validating valid and invalid cases for all models."""

import pytest
from pydantic import ValidationError
from videograph.schemas import (
    Segment,
    Chunk,
    Entity,
    Relation,
    ChunkExtraction,
    Chapter,
)


# --- Segment Tests ---
def test_valid_segment():
    seg = Segment(id=1, start=10.0, end=15.5, text="Hello world")
    assert seg.start == 10.0
    assert seg.end == 15.5
    assert seg.timestamp_str == "00:10"


def test_invalid_segment_time_range():
    with pytest.raises(ValidationError) as exc:
        Segment(start=20.0, end=10.0, text="Invalid time")
    assert "start (20.0) must be <= end (10.0)" in str(exc.value)


# --- Chunk Tests ---
def test_valid_chunk():
    seg = Segment(start=0.0, end=5.0, text="Intro segment")
    chunk = Chunk(id=0, start=0.0, end=5.0, segments=[seg], text="Intro segment")
    assert chunk.id == 0
    assert len(chunk.segments) == 1


def test_invalid_chunk_time_range():
    with pytest.raises(ValidationError) as exc:
        Chunk(id=1, start=30.0, end=15.0, segments=[], text="Backwards")
    assert "start (30.0) must be <= end (15.0)" in str(exc.value)


# --- Entity Tests ---
def test_valid_entity():
    ent = Entity(name="Attention Mechanism", type="Concept", aliases=["Self-Attention", "Dot-Product Attention"])
    assert ent.name == "Attention Mechanism"
    assert "Self-Attention" in ent.aliases


# --- Relation Tests ---
def test_valid_relation():
    rel = Relation(
        subject="Transformer",
        predicate="USES",
        object="Attention",
        quote="The transformer architecture relies entirely on attention mechanisms.",
        start_sec=12.0,
        end_sec=18.0,
    )
    assert rel.subject == "Transformer"
    assert rel.start_sec <= rel.end_sec


def test_invalid_relation_time_range():
    with pytest.raises(ValidationError) as exc:
        Relation(
            subject="A",
            predicate="USES",
            object="B",
            quote="Valid short quote.",
            start_sec=25.0,
            end_sec=20.0,
        )
    assert "start_sec (25.0) must be <= end_sec (20.0)" in str(exc.value)


def test_invalid_relation_quote_word_count_exceeded():
    long_quote = " ".join([f"word{i}" for i in range(26)])  # 26 words > 25
    with pytest.raises(ValidationError) as exc:
        Relation(
            subject="A",
            predicate="USES",
            object="B",
            quote=long_quote,
            start_sec=0.0,
            end_sec=5.0,
        )
    assert "quote exceeds max 25 words" in str(exc.value)


def test_relation_quote_max_word_boundary():
    # Exactly 25 words should pass
    exact_quote = " ".join([f"word{i}" for i in range(25)])
    rel = Relation(
        subject="A",
        predicate="USES",
        object="B",
        quote=exact_quote,
        start_sec=1.0,
        end_sec=4.0,
    )
    assert len(rel.quote.split()) == 25


# --- ChunkExtraction Tests ---
def test_valid_chunk_extraction():
    ent1 = Entity(name="Transformer", type="Technology")
    ent2 = Entity(name="Self-Attention", type="Concept", aliases=["Attention"])
    rel = Relation(
        subject="Transformer",
        predicate="USES",
        object="Attention",
        quote="Transformers use attention",
        start_sec=5.0,
        end_sec=10.0,
    )
    extraction = ChunkExtraction(entities=[ent1, ent2], relations=[rel])
    assert len(extraction.entities) == 2
    assert len(extraction.relations) == 1


def test_invalid_chunk_extraction_missing_subject():
    ent = Entity(name="Attention", type="Concept")
    rel = Relation(
        subject="Transformer",  # Not in entities
        predicate="USES",
        object="Attention",
        quote="Transformers use attention",
        start_sec=5.0,
        end_sec=10.0,
    )
    with pytest.raises(ValidationError) as exc:
        ChunkExtraction(entities=[ent], relations=[rel])
    assert "Relation subject 'Transformer' does not exist in extracted entities" in str(exc.value)


def test_invalid_chunk_extraction_missing_object():
    ent = Entity(name="Transformer", type="Technology")
    rel = Relation(
        subject="Transformer",
        predicate="USES",
        object="Recurrence",  # Not in entities
        quote="Transformers replace recurrence",
        start_sec=5.0,
        end_sec=10.0,
    )
    with pytest.raises(ValidationError) as exc:
        ChunkExtraction(entities=[ent], relations=[rel])
    assert "Relation object 'Recurrence' does not exist in extracted entities" in str(exc.value)


# --- Chapter Tests ---
def test_valid_chapter():
    chap = Chapter(title="Introduction", start_sec=0.0, summary="Overview of sequence models.")
    assert chap.title == "Introduction"
    assert chap.start_sec == 0.0
