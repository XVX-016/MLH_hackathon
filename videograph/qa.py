"""Question-Answering module with FAISS dense retrieval and grounded citation verification.

Pipeline:
1. Index transcript segments into FAISS index using SentenceTransformers.
2. Search top-k segments semantically relevant to question.
3. Prompt LLM for structured answer with citations.
4. Verify every citation against transcript text with RapidFuzz + timestamps.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import numpy as np

from videograph.schemas import TranscriptSegment, QAResponse, QACitation
from videograph.prompts import GROUNDED_QA_PROMPT
from videograph.llm import call_llm_json
from videograph.grounding import get_embed_model, verify_citation


class TranscriptRetriever:
    """FAISS-based dense semantic retriever over video transcript segments."""

    def __init__(self, segments: List[TranscriptSegment]):
        self.segments = segments
        self.index = None
        self.dimension = 384
        self._build_index()

    def _build_index(self) -> None:
        if not self.segments:
            return

        embedder = get_embed_model()
        if embedder is None:
            return

        import faiss

        texts = [s.text for s in self.segments]
        embeddings = embedder.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        self.dimension = embeddings.shape[1]

        # Inner product on normalized vectors = cosine similarity
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings.astype(np.float32))

    def retrieve(self, query: str, top_k: int = 5) -> List[TranscriptSegment]:
        """Retrieve most relevant transcript segments for a query."""
        if not self.segments:
            return []

        embedder = get_embed_model()
        if self.index is None or embedder is None:
            # Fallback: simple keyword or prefix match
            return self.segments[:top_k]

        q_vec = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        scores, indices = self.index.search(q_vec.astype(np.float32), min(top_k, len(self.segments)))

        results = []
        for idx in indices[0]:
            if 0 <= idx < len(self.segments):
                results.append(self.segments[idx])
        return results


def answer_question(
    question: str,
    segments: List[TranscriptSegment],
    model: str = "gemma-4-it",
    top_k: int = 6,
) -> QAResponse:
    """Generate grounded answer with timestamped, verified citations."""
    if not segments:
        return QAResponse(
            question=question,
            answer="No transcript segments are available for this video.",
            citations=[],
            grounded=False,
        )

    retriever = TranscriptRetriever(segments)
    top_segments = retriever.retrieve(question, top_k=top_k)

    # Format snippets for prompt
    snippets = []
    for s in top_segments:
        snippets.append(f"[{s.timestamp_str}] (start={s.start:.1f}s, end={s.end:.1f}s): {s.text}")
    context_text = "\n".join(snippets)

    prompt = GROUNDED_QA_PROMPT.format(
        context_snippets=context_text,
        question=question,
    )

    qa_output = call_llm_json(prompt, QAResponse, model=model)
    qa_output.question = question

    # Verify each citation against the full transcript
    verified_citations: List[QACitation] = []
    all_verified = True

    for cit in qa_output.citations:
        v_cit = verify_citation(cit, segments)
        verified_citations.append(v_cit)
        if not v_cit.verified:
            all_verified = False

    qa_output.citations = verified_citations
    qa_output.grounded = all_verified if verified_citations else False

    return qa_output
