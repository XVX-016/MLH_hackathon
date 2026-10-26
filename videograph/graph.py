"""NetworkX and vis-network representations of evidence-grounded graphs."""

from __future__ import annotations

from html import escape
from typing import Any, Dict, Iterable, Union

import networkx as nx

from videograph.resolve import ResolvedExtraction
from videograph.schemas import ChunkExtraction, KnowledgeGraph

GraphInput = Union[KnowledgeGraph, ChunkExtraction, ResolvedExtraction]


def _extraction(source: GraphInput) -> ChunkExtraction | None:
    if isinstance(source, ResolvedExtraction):
        return source.extraction
    if isinstance(source, ChunkExtraction):
        return source
    return None


def _add_communities(graph: nx.MultiDiGraph) -> None:
    """Attach deterministic Louvain community numbers to every graph node."""
    if not graph.nodes:
        return
    undirected = nx.Graph()
    undirected.add_nodes_from(graph.nodes)
    undirected.add_edges_from((source, target) for source, target in graph.edges())
    communities = nx.community.louvain_communities(undirected, seed=0)
    for index, members in enumerate(communities):
        for node_id in members:
            graph.nodes[node_id]["community"] = index


def build_networkx_graph(source: GraphInput) -> nx.MultiDiGraph:
    """Build a MultiDiGraph with evidence lists and node mention timestamps."""
    graph = nx.MultiDiGraph()
    extraction = _extraction(source)
    if extraction is not None:
        for entity in extraction.entities:
            graph.add_node(
                entity.name,
                label=entity.name,
                type=entity.type,
                aliases=entity.aliases,
                mentions=[],
            )
        for relation in extraction.relations:
            evidence = {
                "quote": relation.quote,
                "start": relation.start_sec,
                "end": relation.end_sec,
            }
            for name in (relation.subject, relation.object):
                if name not in graph:
                    graph.add_node(name, label=name, type="Concept", aliases=[], mentions=[])
                graph.nodes[name]["mentions"].append(relation.start_sec)
            graph.add_edge(
                relation.subject,
                relation.object,
                relation=relation.predicate,
                evidence=[evidence],
            )
    else:
        assert isinstance(source, KnowledgeGraph)
        for node in source.nodes:
            graph.add_node(
                node.id,
                label=node.label,
                type=node.type,
                description=node.description or "",
                mentions=[],
            )
        for edge in source.edges:
            evidence = {"quote": edge.evidence_quote, "start": edge.start_time, "end": edge.end_time}
            for node_id in (edge.source, edge.target):
                if node_id not in graph:
                    graph.add_node(node_id, label=node_id, type="Concept", mentions=[])
                graph.nodes[node_id]["mentions"].append(edge.start_time)
            graph.add_edge(edge.source, edge.target, relation=edge.relation, evidence=[evidence], confidence=edge.confidence)

    for _, attrs in graph.nodes(data=True):
        attrs["mentions"] = sorted(set(attrs["mentions"]))
    _add_communities(graph)
    return graph


def compute_louvain_communities(source: GraphInput) -> Dict[str, int]:
    """Return a node-to-community mapping computed with Louvain clustering."""
    graph = build_networkx_graph(source)
    return {node_id: attrs["community"] for node_id, attrs in graph.nodes(data=True)}


def compute_graph_metrics(source: GraphInput) -> Dict[str, Any]:
    """Calculate basic graph statistics and centrality scores."""
    graph = build_networkx_graph(source)
    if not graph.nodes:
        return {"num_nodes": 0, "num_edges": 0, "centrality": {}}
    simple_graph = nx.DiGraph(graph)
    degree = nx.degree_centrality(simple_graph)
    betweenness = nx.betweenness_centrality(simple_graph)
    return {
        "num_nodes": graph.number_of_nodes(),
        "num_edges": graph.number_of_edges(),
        "top_entities": [
            {"id": node_id, "score": round(score, 3)}
            for node_id, score in sorted(degree.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "degree_centrality": {node_id: round(score, 3) for node_id, score in degree.items()},
        "betweenness_centrality": {node_id: round(score, 3) for node_id, score in betweenness.items()},
        "communities": {node_id: attrs["community"] for node_id, attrs in graph.nodes(data=True)},
    }


def _timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def to_vis_network_data(source: GraphInput) -> Dict[str, Any]:
    """Export graph data in vis-network's ``{nodes, edges}`` format."""
    graph = build_networkx_graph(source)
    colors = {
        "concept": "#6366f1", "technology": "#06b6d4", "tool": "#10b981",
        "person": "#f59e0b", "organization": "#ec4899", "method": "#8b5cf6",
    }
    nodes = [
        {
            "id": node_id,
            "label": attrs["label"],
            "title": f"<b>{escape(attrs['label'])}</b><br>Mentions: {', '.join(_timestamp(time) for time in attrs['mentions']) or 'none'}",
            "size": 16 + 4 * graph.degree(node_id),
            "group": attrs["type"],
            "color": colors.get(attrs["type"].casefold(), "#6366f1"),
            "mentions": attrs["mentions"],
            "community": attrs["community"],
        }
        for node_id, attrs in graph.nodes(data=True)
    ]
    edges = []
    for index, (source_id, target_id, attrs) in enumerate(graph.edges(data=True)):
        evidence = attrs["evidence"]
        first = evidence[0]
        edges.append(
            {
                "id": f"e_{index}_{source_id}_{target_id}",
                "from": source_id,
                "to": target_id,
                "label": attrs["relation"],
                "title": escape(first["quote"]),
                "arrows": "to",
                "evidence": evidence,
                # Compatibility fields for the existing browser evidence drawer.
                "evidence_quote": first["quote"],
                "start_time": first["start"],
                "end_time": first["end"],
                "timestamp_str": _timestamp(first["start"]),
                "confidence": attrs.get("confidence", 1.0),
            }
        )
    return {"nodes": nodes, "edges": edges}
