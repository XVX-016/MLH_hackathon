"""Comprehensive pytest test suite for videograph modules.

Validates schemas, chunking, VTT transcription parsing, grounding verification,
entity resolution, and NetworkX Vis.js graph transformations.
"""

import pytest
from videograph.schemas import (
    TranscriptSegment,
    VideoChapter,
    KnowledgeNode,
    KnowledgeEdge,
    KnowledgeGraph,
    QACitation,
    QAResponse,
)
from videograph.chunk import chunk_transcript
from videograph.transcribe import parse_vtt_or_srt
from videograph.grounding import find_best_transcript_alignment, verify_knowledge_edge, verify_citation
from videograph.resolve import fast_fuzzy_clustering, resolve_knowledge_graph
from videograph.graph import build_networkx_graph, to_vis_network_data, compute_graph_metrics


def test_transcript_segment_schema():
    seg = TranscriptSegment(id=1, start=125.0, end=130.0, text="Attention is all you need.")
    assert seg.timestamp_str == "02:05"
    assert seg.id == 1
    assert seg.start == 125.0


def test_chunking_logic():
    segments = [
        TranscriptSegment(id=i, start=float(i * 10), end=float((i + 1) * 10), text=f"Sentence {i}")
        for i in range(15)  # 150 seconds total
    ]
    chunks = chunk_transcript(segments, target_duration_sec=60.0, overlap_duration_sec=15.0)
    assert len(chunks) >= 2
    assert chunks[0].start == 0.0
    assert "Sentence 0" in chunks[0].text


def test_vtt_parsing():
    vtt_sample = """WEBVTT

00:00:01.000 --> 00:00:04.500
Hello and welcome to videograph.

00:00:05.000 --> 00:00:09.200
We extract knowledge graphs from videos.
"""
    segments = parse_vtt_or_srt(vtt_sample)
    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].end == 4.5
    assert "videograph" in segments[0].text
    assert segments[1].start == 5.0


def test_grounding_alignment_and_verification():
    segments = [
        TranscriptSegment(id=0, start=10.0, end=20.0, text="Transformers use multi-head self-attention mechanisms."),
        TranscriptSegment(id=1, start=20.0, end=30.0, text="FlashAttention optimizes GPU memory bandwidth."),
    ]

    # Test exact quote verification
    verified, score, start, end = find_best_transcript_alignment(
        "Transformers use multi-head self-attention", segments
    )
    assert verified is True
    assert score >= 90.0
    assert start == 10.0

    # Test edge verification
    edge = KnowledgeEdge(
        source="transformer",
        target="attention",
        relation="USES",
        evidence_quote="Transformers use multi-head self-attention mechanisms",
        start_time=0.0,
        end_time=0.0,
        confidence=1.0,
    )
    verified_edge = verify_knowledge_edge(edge, segments)
    assert verified_edge.confidence >= 0.8
    assert verified_edge.start_time == 10.0


def test_entity_resolution_and_deduplication():
    nodes = [
        KnowledgeNode(id="transformer", label="Transformer", type="Technology"),
        KnowledgeNode(id="transformers", label="Transformers", type="Technology"),
        KnowledgeNode(id="rnn", label="Recurrent Neural Network", type="Technology"),
    ]
    edges = [
        KnowledgeEdge(
            source="transformers",
            target="rnn",
            relation="REPLACES",
            evidence_quote="Transformers replace RNNs",
            start_time=10.0,
            end_time=15.0,
        )
    ]
    graph = KnowledgeGraph(nodes=nodes, edges=edges)
    resolved = resolve_knowledge_graph(graph)

    # "Transformer" and "Transformers" should be clustered into one canonical entity
    node_ids = [n.id for n in resolved.nodes]
    assert len(node_ids) == 2
    assert resolved.edges[0].source in node_ids


def test_graph_networkx_and_vis_export():
    nodes = [
        KnowledgeNode(id="n1", label="Node 1", type="Concept"),
        KnowledgeNode(id="n2", label="Node 2", type="Technology"),
    ]
    edges = [
        KnowledgeEdge(
            source="n1",
            target="n2",
            relation="CONNECTS",
            evidence_quote="Node 1 connects to Node 2",
            start_time=5.0,
            end_time=8.0,
            confidence=0.95,
        )
    ]
    graph = KnowledgeGraph(nodes=nodes, edges=edges)
    nx_g = build_networkx_graph(graph)
    assert nx_g.number_of_nodes() == 2
    assert nx_g.number_of_edges() == 1

    vis_data = to_vis_network_data(graph)
    assert len(vis_data["nodes"]) == 2
    assert len(vis_data["edges"]) == 1
    assert vis_data["edges"][0]["from"] == "n1"
    assert "evidence_quote" in vis_data["edges"][0]

    metrics = compute_graph_metrics(graph)
    assert metrics["num_nodes"] == 2
    assert metrics["num_edges"] == 1
