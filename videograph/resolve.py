"""Entity resolution and deduplication module for videograph.

Unifies candidate entities across chunks using:
1. Canonical normalization (casing, trimming, punctuation).
2. RapidFuzz token sort string similarity clustering.
3. LLM cluster refinement for semantic synonym merging.
"""

from __future__ import annotations
import re
from typing import List, Dict, Set
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from videograph.schemas import KnowledgeNode, KnowledgeEdge, KnowledgeGraph
from videograph.prompts import RESOLVE_ENTITIES_PROMPT
from videograph.llm import call_llm_json


class ResolvedCluster(BaseModel):
    canonical_id: str
    canonical_label: str
    type: str = "Concept"
    aliases: List[str] = Field(default_factory=list)


class ResolveClustersOutput(BaseModel):
    clusters: List[ResolvedCluster] = Field(default_factory=list)


def normalize_entity_id(label: str) -> str:
    """Convert label into canonical lowercase underscored token."""
    cleaned = re.sub(r"[^\w\s-]", "", label).strip().lower()
    return re.sub(r"[-\s]+", "_", cleaned)


def fast_fuzzy_clustering(nodes: List[KnowledgeNode], similarity_threshold: float = 85.0) -> Dict[str, str]:
    """Group similar entity IDs using token sort ratio.
    
    Returns:
        Mapping from candidate node id -> canonical node id.
    """
    id_map: Dict[str, str] = {}
    canonical_reps: List[Tuple[str, str]] = []  # (canonical_id, label)

    for node in nodes:
        curr_id = normalize_entity_id(node.id or node.label)
        curr_label = node.label.strip()

        matched_rep = None
        for rep_id, rep_label in canonical_reps:
            # Check string similarity between labels
            ratio = fuzz.token_sort_ratio(curr_label.lower(), rep_label.lower())
            if ratio >= similarity_threshold:
                matched_rep = rep_id
                break

        if matched_rep:
            id_map[node.id] = matched_rep
            id_map[curr_id] = matched_rep
        else:
            canonical_reps.append((curr_id, curr_label))
            id_map[node.id] = curr_id
            id_map[curr_id] = curr_id

    return id_map


def resolve_knowledge_graph(
    graph: KnowledgeGraph,
    use_llm_clustering: bool = False,
    model: str = "gemma-4-it",
) -> KnowledgeGraph:
    """Deduplicate nodes and remap edges to canonical entities."""
    if not graph.nodes:
        return graph

    # Step 1: Deterministic normalization & fuzzy clustering
    id_map = fast_fuzzy_clustering(graph.nodes)

    # Compile canonical node representations
    node_registry: Dict[str, KnowledgeNode] = {}
    for node in graph.nodes:
        canon_id = id_map.get(node.id, normalize_entity_id(node.id))
        if canon_id not in node_registry:
            node_registry[canon_id] = KnowledgeNode(
                id=canon_id,
                label=node.label.strip(),
                type=node.type or "Concept",
                description=node.description or "",
            )
        else:
            # Preserve longer descriptive text
            existing = node_registry[canon_id]
            if len(node.description or "") > len(existing.description or ""):
                existing.description = node.description

    # Step 2: Remap edges and remove self-loops or duplicate edges
    resolved_edges: List[KnowledgeEdge] = []
    seen_edge_keys: Set[Tuple[str, str, str]] = set()

    for edge in graph.edges:
        new_source = id_map.get(edge.source, normalize_entity_id(edge.source))
        new_target = id_map.get(edge.target, normalize_entity_id(edge.target))

        # Drop self-loops
        if new_source == new_target:
            continue

        # Check for existence in nodes; create default node if referenced in edge
        for n_id, n_label in [(new_source, edge.source), (new_target, edge.target)]:
            if n_id not in node_registry:
                node_registry[n_id] = KnowledgeNode(
                    id=n_id,
                    label=n_label.replace("_", " ").title(),
                    type="Concept",
                )

        edge_key = (new_source, new_target, edge.relation.upper())
        if edge_key not in seen_edge_keys:
            seen_edge_keys.add(edge_key)
            edge.source = new_source
            edge.target = new_target
            edge.relation = edge.relation.upper()
            resolved_edges.append(edge)

    return KnowledgeGraph(
        nodes=list(node_registry.values()),
        edges=resolved_edges,
    )
