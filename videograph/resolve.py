"""Deterministic entity resolution for extracted knowledge."""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from videograph.schemas import ChunkExtraction, Entity, KnowledgeGraph, KnowledgeNode

FUZZY_MATCH_THRESHOLD = 90.0
MIN_FUZZY_NAME_LENGTH = 5


class ResolvedExtraction(BaseModel):
    """Resolved extraction plus a source-name-to-canonical-name debug map."""

    extraction: ChunkExtraction
    merge_map: Dict[str, str] = Field(default_factory=dict)


def normalize_entity_id(label: str) -> str:
    """Return a comparison key insensitive to spacing and punctuation."""
    return re.sub(r"[^\w]", "", label.casefold())


def _entity_terms(entity: Entity) -> Set[str]:
    """Return normalized entity name and aliases, excluding blank values."""
    return {term for value in [entity.name, *entity.aliases] if (term := normalize_entity_id(value))}


def _same_type(first: Entity, second: Entity) -> bool:
    return first.type.strip().casefold() == second.type.strip().casefold()


def _matches_entity(candidate: Entity, canonical: Entity) -> bool:
    """Match by normalized names/aliases, then conservatively by fuzzy score."""
    candidate_terms = _entity_terms(candidate)
    canonical_terms = _entity_terms(canonical)
    if candidate_terms & canonical_terms:
        return True
    return any(
        min(len(left), len(right)) >= MIN_FUZZY_NAME_LENGTH
        and fuzz.ratio(left, right) >= FUZZY_MATCH_THRESHOLD
        for left in candidate_terms
        for right in canonical_terms
    )


def resolve_chunk_extraction(extraction: ChunkExtraction) -> ResolvedExtraction:
    """Merge same-type entities and rewrite relation endpoints canonically."""
    canonical_entities: List[Entity] = []
    merge_map: Dict[str, str] = {}
    term_map: Dict[str, str] = {}

    for entity in extraction.entities:
        match = next(
            (
                canonical
                for canonical in canonical_entities
                if _same_type(entity, canonical) and _matches_entity(entity, canonical)
            ),
            None,
        )
        if match is None:
            match = entity.model_copy(deep=True)
            canonical_entities.append(match)
        else:
            aliases = [*match.aliases, entity.name, *entity.aliases]
            match.aliases = list(dict.fromkeys(alias for alias in aliases if alias != match.name))

        merge_map[entity.name] = match.name
        for term in _entity_terms(entity) | _entity_terms(match):
            term_map[term] = match.name

    def canonical_name(name: str) -> str:
        return term_map.get(normalize_entity_id(name), name)

    relations = [
        relation.model_copy(
            update={
                "subject": canonical_name(relation.subject),
                "object": canonical_name(relation.object),
            }
        )
        for relation in extraction.relations
    ]
    return ResolvedExtraction(
        extraction=ChunkExtraction(entities=canonical_entities, relations=relations),
        merge_map=merge_map,
    )


resolve_extraction = resolve_chunk_extraction


def fast_fuzzy_clustering(
    nodes: List[KnowledgeNode], similarity_threshold: float = FUZZY_MATCH_THRESHOLD
) -> Dict[str, str]:
    """Return a type-aware mapping from node IDs to canonical node IDs."""
    representatives: List[KnowledgeNode] = []
    id_map: Dict[str, str] = {}
    for node in nodes:
        node_key = normalize_entity_id(node.label)
        match = next(
            (
                representative
                for representative in representatives
                if representative.type.casefold() == node.type.casefold()
                and (
                    normalize_entity_id(representative.label) == node_key
                    or (
                        min(len(normalize_entity_id(representative.label)), len(node_key))
                        >= MIN_FUZZY_NAME_LENGTH
                        and fuzz.ratio(normalize_entity_id(representative.label), node_key)
                        >= similarity_threshold
                    )
                )
            ),
            None,
        )
        canonical_id = match.id if match else normalize_entity_id(node.id or node.label)
        if match is None:
            representatives.append(node)
        id_map[node.id] = canonical_id
        id_map[normalize_entity_id(node.id)] = canonical_id
    return id_map


def resolve_knowledge_graph(
    graph: KnowledgeGraph,
    use_llm_clustering: bool = False,
    model: str = "gemma-4-it",
) -> KnowledgeGraph:
    """Deduplicate graph nodes and rewrite edges to canonical node IDs."""
    # Kept for API compatibility. Resolution is deliberately deterministic so
    # canonical names and the debugging map remain reproducible.
    del use_llm_clustering, model
    id_map = fast_fuzzy_clustering(graph.nodes)
    nodes: Dict[str, KnowledgeNode] = {}
    for node in graph.nodes:
        canonical_id = id_map[node.id]
        if canonical_id not in nodes:
            nodes[canonical_id] = node.model_copy(update={"id": canonical_id})

    seen_edges: Set[Tuple[str, str, str]] = set()
    edges = []
    for edge in graph.edges:
        source = id_map.get(edge.source, normalize_entity_id(edge.source))
        target = id_map.get(edge.target, normalize_entity_id(edge.target))
        if source == target:
            continue
        key = (source, target, edge.relation.upper())
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(edge.model_copy(update={"source": source, "target": target, "relation": edge.relation.upper()}))
    return KnowledgeGraph(nodes=list(nodes.values()), edges=edges)
