"""FAISS retrieval and strictly grounded question answering."""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Protocol, Sequence, Tuple

import numpy as np
from pydantic import BaseModel, Field

from videograph.grounding import get_embed_model, is_grounded
from videograph.llm import call_llm_json
from videograph.prompts import GROUNDED_QA_PROMPT
from videograph.schemas import KnowledgeGraph, QACitation, QAResponse, TranscriptSegment

NO_CONTEXT_ANSWER = "I couldn't find relevant evidence in the transcript."
DEFAULT_SIMILARITY_THRESHOLD = 0.25


class QAOutput(BaseModel):
    """The LLM-owned portion of a grounded QA response."""

    answer: str
    citations: List[QACitation] = Field(default_factory=list)


class Embedder(Protocol):
    def encode(self, texts: Sequence[str], *, convert_to_numpy: bool, normalize_embeddings: bool) -> np.ndarray:
        ...


class TranscriptRetriever:
    """A per-request FAISS index over timestamped transcript chunks."""

    def __init__(self, segments: List[TranscriptSegment], embedder: Optional[Embedder] = None):
        self.segments = segments
        self.embedder = embedder or get_embed_model()
        self.index = None
        if self.segments and self.embedder is not None:
            self._build_index()

    def _build_index(self) -> None:
        import faiss

        embeddings = self.embedder.encode(
            [segment.text for segment in self.segments],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype(np.float32)
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)

    def retrieve(self, question: str, top_k: int = 5) -> List[Tuple[TranscriptSegment, float]]:
        """Return the highest-scoring chunks and cosine similarities."""
        if self.index is None or self.embedder is None:
            return []
        query = self.embedder.encode(
            [question], convert_to_numpy=True, normalize_embeddings=True
        ).astype(np.float32)
        scores, indices = self.index.search(query, min(top_k, len(self.segments)))
        return [
            (self.segments[index], float(score))
            for score, index in zip(scores[0], indices[0])
            if 0 <= index < len(self.segments)
        ]


def _timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def _mentioned_node_ids(segments: Sequence[TranscriptSegment], graph: KnowledgeGraph) -> set[str]:
    """Find graph nodes whose label or identifier occurs in retrieved text."""
    text = " ".join(segment.text.casefold() for segment in segments)
    mentions = set()
    for node in graph.nodes:
        candidates = (node.label, node.id.replace("_", " "))
        if any(re.search(rf"(?<!\w){re.escape(candidate.casefold())}(?!\w)", text) for candidate in candidates):
            mentions.add(node.id)
    return mentions


def _one_hop_facts(segments: Sequence[TranscriptSegment], graph: Optional[KnowledgeGraph]) -> List[str]:
    if graph is None:
        return []
    mentioned = _mentioned_node_ids(segments, graph)
    labels = {node.id: node.label for node in graph.nodes}
    facts = []
    for edge in graph.edges:
        if edge.source in mentioned or edge.target in mentioned:
            facts.append(
                f"{labels.get(edge.source, edge.source)} -{edge.relation}-> "
                f"{labels.get(edge.target, edge.target)} [{_timestamp(edge.start_time)}]"
            )
    return facts


def build_qa_context(retrieved: Sequence[Tuple[TranscriptSegment, float]], graph: Optional[KnowledgeGraph]) -> str:
    """Format retrieved transcript chunks and their one-hop graph facts."""
    segments = [segment for segment, _ in retrieved]
    transcript = [
        f"[{segment.timestamp_str}] (start={segment.start:.1f}s, end={segment.end:.1f}s): {segment.text}"
        for segment in segments
    ]
    facts = _one_hop_facts(segments, graph)
    return "\n".join([*transcript, *( ["Graph facts:", *facts] if facts else [])])


def answer_question(
    question: str,
    segments: List[TranscriptSegment],
    graph: Optional[KnowledgeGraph] = None,
    model: str = "gemma-4-it",
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    llm_call: Callable[[str, type[QAOutput], str], QAOutput] = call_llm_json,
) -> QAResponse:
    """Answer only when semantic retrieval finds sufficiently relevant evidence."""
    retrieved = TranscriptRetriever(segments).retrieve(question, top_k=5)
    passing = [(segment, score) for segment, score in retrieved if score >= similarity_threshold]
    if not passing:
        return QAResponse(question=question, answer=NO_CONTEXT_ANSWER, citations=[], grounded=False)

    prompt = GROUNDED_QA_PROMPT.format(context_snippets=build_qa_context(passing, graph), question=question)
    output = llm_call(prompt, QAOutput, model)
    verified = [
        citation.model_copy(update={"verified": True})
        for citation in output.citations
        if is_grounded(citation.quote, segments, citation.start_time, citation.end_time)
    ]
    if not verified:
        return QAResponse(question=question, answer=NO_CONTEXT_ANSWER, citations=[], grounded=False)
    return QAResponse(
        question=question,
        answer=output.answer,
        citations=verified,
        grounded=bool(verified),
    )
