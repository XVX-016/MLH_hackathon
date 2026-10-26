"""Tests for type-aware entity resolution."""

from videograph.resolve import resolve_chunk_extraction
from videograph.schemas import ChunkExtraction, Entity, Relation


def _relation(subject: str, object_: str) -> Relation:
    return Relation(
        subject=subject,
        predicate="USES",
        object=object_,
        quote="GPT-4 uses a transformer architecture.",
        start_sec=0.0,
        end_sec=4.0,
    )


def test_resolve_merges_punctuation_variants_and_rewrites_relations() -> None:
    extraction = ChunkExtraction(
        entities=[
            Entity(name="GPT-4", type="Model"),
            Entity(name="GPT 4", type="Model"),
            Entity(name="Transformer", type="Architecture"),
        ],
        relations=[_relation("GPT 4", "Transformer")],
    )

    resolved = resolve_chunk_extraction(extraction)

    assert [entity.name for entity in resolved.extraction.entities] == ["GPT-4", "Transformer"]
    assert resolved.extraction.relations[0].subject == "GPT-4"
    assert resolved.merge_map["GPT 4"] == "GPT-4"


def test_resolve_does_not_merge_matching_names_of_different_types() -> None:
    extraction = ChunkExtraction(
        entities=[Entity(name="Apple", type="Company"), Entity(name="Apple", type="Fruit")]
    )

    assert len(resolve_chunk_extraction(extraction).extraction.entities) == 2


def test_resolve_does_not_fuzzily_merge_short_distinct_names() -> None:
    extraction = ChunkExtraction(
        entities=[Entity(name="ABC", type="Concept"), Entity(name="ABD", type="Concept")]
    )

    assert len(resolve_chunk_extraction(extraction).extraction.entities) == 2
