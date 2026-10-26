"""Tests for FAISS-backed, citation-grounded Q&A."""

import numpy as np

import videograph.qa as qa
from videograph.schemas import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, QACitation, TranscriptSegment


class FakeEmbedder:
    def encode(self, texts, *, convert_to_numpy, normalize_embeddings):
        # Deterministic cosine-compatible vectors; the first segment is relevant.
        return np.array([[1.0, 0.0] if "attention" in text.lower() else [0.0, 1.0] for text in texts])


def test_answer_question_adds_graph_context_and_drops_bad_citations(monkeypatch) -> None:
    segments = [
        TranscriptSegment(id=0, start=10.0, end=15.0, text="Transformers use attention mechanisms."),
        TranscriptSegment(id=1, start=30.0, end=35.0, text="A separate conclusion."),
    ]
    graph = KnowledgeGraph(
        nodes=[KnowledgeNode(id="transformer", label="Transformers"), KnowledgeNode(id="attention", label="attention")],
        edges=[KnowledgeEdge(source="transformer", target="attention", relation="USES", evidence_quote="Transformers use attention mechanisms.", start_time=10.0, end_time=15.0)],
    )
    monkeypatch.setattr(qa, "get_embed_model", lambda: FakeEmbedder())
    captured = {}

    def fake_llm(prompt, schema, model):
        captured["prompt"] = prompt
        return qa.QAOutput(
            answer="Transformers use attention [00:10].",
            citations=[
                QACitation(timestamp_str="00:10", start_time=10.0, end_time=15.0, quote="Transformers use attention mechanisms."),
                QACitation(timestamp_str="00:10", start_time=10.0, end_time=15.0, quote="Invented on Mars."),
            ],
        )

    response = qa.answer_question("How does attention work?", segments, graph=graph, llm_call=fake_llm)

    assert "Transformers -USES-> attention [00:10]" in captured["prompt"]
    assert len(response.citations) == 1
    assert response.citations[0].verified is True
    assert response.grounded is True


def test_answer_question_returns_not_found_when_no_similarity_passes(monkeypatch) -> None:
    monkeypatch.setattr(qa, "get_embed_model", lambda: FakeEmbedder())
    segments = [TranscriptSegment(id=0, start=0.0, end=2.0, text="Attention is useful.")]

    response = qa.answer_question("unrelated", segments, similarity_threshold=1.1)

    assert response.answer == qa.NO_CONTEXT_ANSWER
    assert response.grounded is False
