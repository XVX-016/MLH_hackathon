"""Knowledge extraction module for videograph.

Extracts:
1. Chapters and executive summary from the full transcript.
2. Knowledge nodes and evidence-grounded edges from transcript chunks.
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Sequence, Tuple
from pydantic import BaseModel, Field, ValidationError

from videograph.schemas import (
    TranscriptSegment,
    VideoChapter,
    Chapter,
    Entity,
    ChunkExtraction,
    Flashcard,
    KnowledgeNode,
    KnowledgeEdge,
    KnowledgeGraph,
)
from videograph.chunk import TranscriptChunk, chunk_transcript
from videograph.prompts import CHAPTERS_PROMPT, SUMMARY_PROMPT, EXTRACTION_PROMPT, EXTRACT_GRAPH_PROMPT, FLASHCARDS_PROMPT
from videograph.llm import call_llm_json, call_llm_raw
from videograph.grounding import verify_knowledge_edge

logger = logging.getLogger(__name__)
EXTRACTION_CACHE_DIR = Path.home() / ".videograph_cache" / "extractions"


class ExtractionClient(Protocol):
    """Small async interface that permits deterministic extraction tests."""

    async def complete(self, prompt: str, model: str) -> str:
        """Return the raw JSON response for an extraction prompt."""
        ...


class GeminiExtractionClient:
    """Adapter around the existing cached Gemini raw-call client."""

    async def complete(self, prompt: str, model: str) -> str:
        return await asyncio.to_thread(call_llm_raw, prompt, model)


def chunk_content_hash(chunk: TranscriptChunk, model: str) -> str:
    """Stable cache key for a chunk's transcript content and selected model."""
    content = json.dumps(
        {"model": model, "start": chunk.start, "end": chunk.end, "text": chunk.formatted_text},
        sort_keys=True,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_extraction_json(raw_text: str) -> ChunkExtraction:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return ChunkExtraction.model_validate(json.loads(stripped.strip()))


def _cache_path(chunk: TranscriptChunk, model: str, cache_dir: Path) -> Path:
    return cache_dir / f"{chunk_content_hash(chunk, model)}.json"


async def extract_chunk(
    chunk: TranscriptChunk,
    client: ExtractionClient,
    model: str = "gemma-4-it",
    cache_dir: Path = EXTRACTION_CACHE_DIR,
) -> Optional[ChunkExtraction]:
    """Extract one chunk, retrying exactly once for malformed/invalid JSON."""
    path = _cache_path(chunk, model, cache_dir)
    if path.exists():
        try:
            return _parse_extraction_json(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValidationError):
            logger.warning("Ignoring invalid extraction cache for chunk %s", chunk.chunk_id)

    prompt = EXTRACTION_PROMPT.format(
        chunk_start=chunk.start,
        chunk_end=chunk.end,
        chunk_text=chunk.formatted_text,
    )
    current_prompt = prompt
    for attempt in range(2):
        try:
            extraction = _parse_extraction_json(await client.complete(current_prompt, model))
            cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(extraction.model_dump_json(), encoding="utf-8")
            return extraction
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            if attempt == 0:
                current_prompt = (
                    f"{prompt}\n\nPrevious response validation error:\n{error}\n"
                    "Return only JSON that satisfies the requested schema."
                )
            else:
                logger.warning("Skipping chunk %s after invalid extraction: %s", chunk.chunk_id, error)
    return None


async def extract_chunks(
    chunks: Sequence[TranscriptChunk],
    client: Optional[ExtractionClient] = None,
    model: str = "gemma-4-it",
    cache_dir: Path = EXTRACTION_CACHE_DIR,
) -> List[ChunkExtraction]:
    """Extract all chunks concurrently, with at most four active LLM calls."""
    extraction_client = client or GeminiExtractionClient()
    semaphore = asyncio.Semaphore(4)

    async def guarded(chunk: TranscriptChunk) -> Optional[ChunkExtraction]:
        async with semaphore:
            return await extract_chunk(chunk, extraction_client, model=model, cache_dir=cache_dir)

    results = await asyncio.gather(*(guarded(chunk) for chunk in chunks))
    return [result for result in results if result is not None]


class ChaptersOutput(BaseModel):
    """Validated chapter-only LLM output."""

    chapters: List[Chapter] = Field(default_factory=list)


class SummaryOutput(BaseModel):
    """Validated summary-only LLM output."""

    summary: str


def build_chunk_gists(
    chunks: Sequence[TranscriptChunk],
    chunk_entities: Optional[Sequence[Sequence[Entity]]] = None,
) -> List[str]:
    """Make compact timestamped gists from each chunk's most salient entities."""
    gists = []
    for index, chunk in enumerate(chunks):
        entities = chunk_entities[index] if chunk_entities and index < len(chunk_entities) else []
        names = list(dict.fromkeys(entity.name for entity in entities))[:5]
        topic = ", ".join(names) if names else "No extracted entities"
        gists.append(f"[{chunk.start:.1f}s] Entities: {topic}. Transcript: {chunk.text[:240]}")
    return gists


MAX_CHAPTER_TITLE_WORDS = 5  # "under 6 words"


def _snap_chapter_starts(chapters: Sequence[Chapter], chunks: Sequence[TranscriptChunk]) -> List[Chapter]:
    """Snap LLM chapter starts to the nearest real chunk start and keep them strictly increasing.

    Models often return 62.0 for a chunk that starts at 61.84; rejecting the whole
    answer for that threw away good chapters. A start further than one chunk
    length from any real start is treated as invented and dropped.
    """
    starts = sorted({chunk.start for chunk in chunks})
    if not starts:
        raise ValueError("No chunks to anchor chapters to")
    tolerance = max((chunk.end - chunk.start) for chunk in chunks)
    snapped: List[Chapter] = []
    for chapter in sorted(chapters, key=lambda item: item.start_sec):
        nearest = min(starts, key=lambda start: abs(start - chapter.start_sec))
        if abs(nearest - chapter.start_sec) > tolerance:
            continue
        if snapped and nearest <= snapped[-1].start_sec:
            continue
        title = " ".join(chapter.title.split()[:MAX_CHAPTER_TITLE_WORDS])
        snapped.append(Chapter(title=title, start_sec=nearest, summary=chapter.summary.strip()))
    if len(snapped) < min(2, len(starts)):
        raise ValueError("Chapters must cover at least two distinct chunk starts")
    return snapped


def _first_sentence(text: str, limit: int = 160) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", " ".join(text.split()), maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rsplit(" ", 1)[0] + "…"


def _fallback_time_chapters(
    chunks: Sequence[TranscriptChunk],
    chunk_entities: Optional[Sequence[Sequence[Entity]]] = None,
    max_chapters: int = 6,
) -> List[Chapter]:
    """Evenly spaced, time-ordered chapters used when the LLM output is unusable."""
    if not chunks:
        return []
    count = min(len(chunks), max_chapters)
    bounds = [round(index * len(chunks) / count) for index in range(count)] + [len(chunks)]
    chapters = []
    for number in range(count):
        group = range(bounds[number], bounds[number + 1])
        names: List[str] = []
        if chunk_entities:
            for index in group:
                if index < len(chunk_entities):
                    names.extend(entity.name for entity in chunk_entities[index])
        names = list(dict.fromkeys(names))[:3]
        text = " ".join(chunks[index].text for index in group)
        if names:
            title = " · ".join(names)
        else:
            words = _first_sentence(text, limit=80).rstrip(".!?…").split()
            title = " ".join(words[:5]) + ("…" if len(words) > 5 else "") if words else f"Part {number + 1}"
        chapters.append(Chapter(title=title, start_sec=chunks[bounds[number]].start, summary=_first_sentence(text)))
    return chapters


def generate_chapters_and_summary(
    chunks: Sequence[TranscriptChunk],
    chunk_entities: Optional[Sequence[Sequence[Entity]]] = None,
    graph: Optional[KnowledgeGraph] = None,
    model: str = "gemma-4-it",
    llm_call: Callable[..., BaseModel] = call_llm_json,
) -> Tuple[str, List[Chapter]]:
    """Generate time-ordered chapters (LLM, else evenly spaced chunk groups), then summarize."""
    if not chunks:
        return "No transcript content is available.", []
    gists = build_chunk_gists(chunks, chunk_entities)
    gist_text = "\n".join(gists)
    try:
        chapters_output = llm_call(CHAPTERS_PROMPT.format(chunk_gists=gist_text), ChaptersOutput, model=model)
        chapters = _snap_chapter_starts(chapters_output.chapters, chunks)
    except (ValueError, TypeError, ValidationError) as error:
        logger.warning("Invalid chapter output; using evenly spaced chapters: %s", error)
        chapters = _fallback_time_chapters(chunks, chunk_entities)

    chapter_text = "\n".join(
        f"[{chapter.start_sec:.1f}s] {chapter.title}: {chapter.summary}" for chapter in chapters
    )
    try:
        summary_output = llm_call(
            SUMMARY_PROMPT.format(chapters=chapter_text, chunk_gists=gist_text), SummaryOutput, model=model
        )
        summary = summary_output.summary
    except (ValueError, TypeError) as error:
        logger.warning("Invalid summary output; using gists: %s", error)
        summary = " ".join(gists)
    return summary, chapters


class FlashcardsOutput(BaseModel):
    """Validated LLM output for per-chunk flashcard extraction."""
    flashcards: List[Flashcard] = Field(default_factory=list)


def generate_flashcards(
    chunks: Sequence[TranscriptChunk],
    model: str = "gemma-4-it",
    llm_call: Callable[..., BaseModel] = call_llm_json,
) -> List[Flashcard]:
    """Extract grounded study flashcards from all transcript chunks.

    Each chunk is sent to the LLM once. On validation failure the chunk is
    skipped and a warning is logged rather than propagating an exception.
    Flashcard ids are reassigned globally to ensure uniqueness.

    Args:
        chunks: Ordered transcript chunks to extract from.
        model: LLM model identifier.
        llm_call: Callable matching call_llm_json signature (injectable for tests).

    Returns:
        Flat list of Flashcard objects across all chunks, with unique sequential ids.
    """
    if not chunks:
        return []

    all_cards: List[Flashcard] = []
    for chunk in chunks:
        prompt = FLASHCARDS_PROMPT.format(
            chunk_start=chunk.start,
            chunk_end=chunk.end,
            chunk_text=chunk.formatted_text,
        )
        try:
            output = llm_call(prompt, FlashcardsOutput, model=model)
            all_cards.extend(output.flashcards)
        except (ValueError, TypeError, ValidationError) as error:
            logger.warning(
                "Skipping flashcard extraction for chunk %s: %s", chunk.chunk_id, error
            )

    # Re-assign sequential ids globally
    for idx, card in enumerate(all_cards):
        card.id = idx
    return all_cards


class RawChunkGraphOutput(BaseModel):
    """Pydantic schema for knowledge extraction per chunk."""
    nodes: List[KnowledgeNode] = Field(default_factory=list)
    edges: List[KnowledgeEdge] = Field(default_factory=list)


def extract_summary_and_chapters(
    segments: List[TranscriptSegment],
    model: str = "gemma-4-it",
) -> Tuple[str, List[VideoChapter]]:
    """Compatibility wrapper for chapter/summary generation from a transcript."""
    return generate_chapters_and_summary(chunk_transcript(segments), model=model)


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
