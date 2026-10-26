"""Knowledge extraction module for videograph.

Extracts:
1. Chapters and executive summary from the full transcript.
2. Knowledge nodes and evidence-grounded edges from transcript chunks.
"""

from __future__ import annotations
from typing import List, Tuple
from pydantic import BaseModel, Field

from videograph.schemas import (
    TranscriptSegment,
    VideoChapter,
    KnowledgeNode,
    KnowledgeEdge,
    KnowledgeGraph,
)
from videograph.chunk import TranscriptChunk
from videograph.prompts import CHAPTERS_AND_SUMMARY_PROMPT, EXTRACT_GRAPH_PROMPT
from videograph.llm import call_llm_json
from videograph.grounding import verify_knowledge_edge


class SummaryAndChaptersOutput(BaseModel):
    """Pydantic schema for summary and chapters LLM output."""
    summary: str
    chapters: List[VideoChapter] = Field(default_factory=list)


class RawChunkGraphOutput(BaseModel):
    """Pydantic schema for knowledge extraction per chunk."""
    nodes: List[KnowledgeNode] = Field(default_factory=list)
    edges: List[KnowledgeEdge] = Field(default_factory=list)


def extract_summary_and_chapters(
    segments: List[TranscriptSegment],
    model: str = "gemma-4-it",
) -> Tuple[str, List[VideoChapter]]:
    """Extract executive summary and chronological chapters from transcript segments."""
    # Build compact timestamped representation
    lines = [f"[{s.timestamp_str}] {s.text}" for s in segments]
    full_text = "\n".join(lines)

    # If transcript is very large, sample or summarize boundaries
    if len(full_text) > 40000:
        full_text = full_text[:40000] + "\n...[truncated for length]"

    prompt = CHAPTERS_AND_SUMMARY_PROMPT.format(transcript_text=full_text)
    result = call_llm_json(prompt, SummaryAndChaptersOutput, model=model)
    return result.summary, result.chapters


def extract_graph_from_chunk(
    chunk: TranscriptChunk,
    all_segments: List[TranscriptSegment],
    model: str = "gemma-4-it",
) -> RawChunkGraphOutput:
    """Extract entities and evidence-grounded edges from a single transcript chunk."""
    prompt = EXTRACT_GRAPH_PROMPT.format(
        chunk_start=chunk.start,
        chunk_end=chunk.end,
        chunk_text=chunk.formatted_text,
    )
    raw_graph = call_llm_json(prompt, RawChunkGraphOutput, model=model)

    # Verify and ground every edge against the actual transcript segments
    verified_edges: List[KnowledgeEdge] = []
    for edge in raw_graph.edges:
        # Enforce valid start/end fallback to chunk boundaries if omitted
        if edge.start_time == 0.0 and edge.end_time == 0.0:
            edge.start_time = chunk.start
            edge.end_time = chunk.end

        edge_verified = verify_knowledge_edge(edge, all_segments)
        # Keep edges that have non-trivial confidence
        if edge_verified.confidence >= 0.2:
            verified_edges.append(edge_verified)

    return RawChunkGraphOutput(nodes=raw_graph.nodes, edges=verified_edges)


def extract_full_graph(
    chunks: List[TranscriptChunk],
    all_segments: List[TranscriptSegment],
    model: str = "gemma-4-it",
) -> KnowledgeGraph:
    """Run extraction across all chunks and compile raw graph."""
    all_nodes: List[KnowledgeNode] = []
    all_edges: List[KnowledgeEdge] = []

    for chunk in chunks:
        chunk_result = extract_graph_from_chunk(chunk, all_segments, model=model)
        all_nodes.extend(chunk_result.nodes)
        all_edges.extend(chunk_result.edges)

    return KnowledgeGraph(nodes=all_nodes, edges=all_edges)
