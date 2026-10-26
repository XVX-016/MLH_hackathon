"""NetworkX graph integration, centrality analysis, and Vis.js serialization.

Converts validated KnowledgeGraph models into NetworkX MultiDiGraph and interactive Vis.js datasets.
"""

from __future__ import annotations
from typing import Dict, Any, List
import networkx as nx

from videograph.schemas import KnowledgeGraph, KnowledgeNode, KnowledgeEdge


def build_networkx_graph(graph: KnowledgeGraph) -> nx.MultiDiGraph:
    """Construct NetworkX MultiDiGraph from KnowledgeGraph."""
    g = nx.MultiDiGraph()

    for node in graph.nodes:
        g.add_node(
            node.id,
            label=node.label,
            type=node.type,
            description=node.description,
        )

    for edge in graph.edges:
        g.add_edge(
            edge.source,
            edge.target,
            relation=edge.relation,
            evidence_quote=edge.evidence_quote,
            start_time=edge.start_time,
            end_time=edge.end_time,
            confidence=edge.confidence,
        )

    return g


def compute_graph_metrics(graph: KnowledgeGraph) -> Dict[str, Any]:
    """Calculate degree, betweenness centrality, and graph statistics."""
    if not graph.nodes:
        return {"num_nodes": 0, "num_edges": 0, "centrality": {}}

    nx_graph = build_networkx_graph(graph)
    # Simple DiGraph for degree / centrality calculation
    simple_digraph = nx.DiGraph(nx_graph)

    degree_cent = nx.degree_centrality(simple_digraph)
    between_cent = nx.betweenness_centrality(simple_digraph)

    # Sort nodes by top degree
    sorted_nodes = sorted(degree_cent.items(), key=lambda x: x[1], reverse=True)

    return {
        "num_nodes": len(graph.nodes),
        "num_edges": len(graph.edges),
        "top_entities": [{"id": k, "score": round(v, 3)} for k, v in sorted_nodes[:10]],
        "degree_centrality": {k: round(v, 3) for k, v in degree_cent.items()},
        "betweenness_centrality": {k: round(v, 3) for k, v in between_cent.items()},
    }


def to_vis_network_data(graph: KnowledgeGraph) -> Dict[str, Any]:
    """Export KnowledgeGraph into Vis.js / vis-network nodes and edges format.
    
    Includes styling, tooltips, and evidence metadata for UI rendering.
    """
    type_color_map = {
        "concept": "#6366f1",       # Indigo
        "technology": "#06b6d4",    # Cyan
        "tech": "#06b6d4",          # Cyan
        "tool": "#10b981",          # Emerald
        "person": "#f59e0b",        # Amber
        "organization": "#ec4899",  # Pink
        "method": "#8b5cf6",        # Purple
    }

    vis_nodes = []
    for node in graph.nodes:
        ntype = (node.type or "concept").lower()
        color = type_color_map.get(ntype, "#6366f1")
        vis_nodes.append({
            "id": node.id,
            "label": node.label,
            "title": f"<b>{node.label}</b> ({node.type})<br/>{node.description}",
            "color": {
                "background": color,
                "border": "#1e293b",
                "highlight": {
                    "background": "#f43f5e",
                    "border": "#ffffff"
                }
            },
            "font": {"color": "#f8fafc", "face": "Inter, sans-serif"},
            "shape": "dot",
            "size": 18,
            "group": node.type,
            "meta": {
                "type": node.type,
                "description": node.description,
            }
        })

    vis_edges = []
    for idx, edge in enumerate(graph.edges):
        m = int(edge.start_time // 60)
        s = int(edge.start_time % 60)
        ts = f"{m:02d}:{s:02d}"

        tooltip = (
            f"<b>Relation:</b> {edge.relation}<br/>"
            f"<b>Evidence:</b> \"{edge.evidence_quote}\"<br/>"
            f"<b>Timestamp:</b> [{ts}] ({edge.start_time:.1f}s - {edge.end_time:.1f}s)<br/>"
            f"<b>Confidence:</b> {edge.confidence * 100:.0f}%"
        )

        vis_edges.append({
            "id": f"e_{idx}_{edge.source}_{edge.target}",
            "from": edge.source,
            "to": edge.target,
            "label": edge.relation,
            "title": tooltip,
            "arrows": "to",
            "color": {"color": "#94a3b8", "highlight": "#38bdf8"},
            "font": {"color": "#cbd5e1", "size": 11, "strokeWidth": 2, "strokeColor": "#0f172a"},
            "evidence_quote": edge.evidence_quote,
            "start_time": edge.start_time,
            "end_time": edge.end_time,
            "timestamp_str": ts,
            "confidence": edge.confidence,
        })

    return {
        "nodes": vis_nodes,
        "edges": vis_edges,
    }
