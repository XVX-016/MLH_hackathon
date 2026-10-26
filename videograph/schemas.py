"""Data schemas for videograph.

All structures use Pydantic v2 with strict validation, custom validators,
and clean serialization.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class Segment(BaseModel):
    """Single timed segment of transcribed video/audio."""
    id: Optional[int] = Field(default=0, description="0-indexed segment sequence number")
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    text: str = Field(..., description="Transcript speech content")

    @field_validator("end")
    @classmethod
    def validate_time_range(cls, end_val: float, info) -> float:
        start_val = info.data.get("start")
        if start_val is not None and start_val > end_val:
            raise ValueError(f"start ({start_val}) must be <= end ({end_val})")
        return end_val

    @property
    def timestamp_str(self) -> str:
        """Formatted [MM:SS] start timestamp."""
        m = int(self.start // 60)
        s = int(self.start % 60)
        return f"{m:02d}:{s:02d}"


# Backwards compatibility alias
TranscriptSegment = Segment


class Chunk(BaseModel):
    """Chunk of contiguous transcript segments with timing metadata."""
    id: int = Field(..., description="Chunk identifier")
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    segments: List[Segment] = Field(default_factory=list, description="List of segments in chunk")
    text: str = Field(..., description="Concatenated text of chunk")

    @field_validator("end")
    @classmethod
    def validate_time_range(cls, end_val: float, info) -> float:
        start_val = info.data.get("start")
        if start_val is not None and start_val > end_val:
            raise ValueError(f"start ({start_val}) must be <= end ({end_val})")
        return end_val


class Entity(BaseModel):
    """Entity node in knowledge graph extraction."""
    name: str = Field(..., description="Canonical entity name")
    type: str = Field(default="Concept", description="Entity category: Concept, Person, Technology, Tool, etc.")
    aliases: List[str] = Field(default_factory=list, description="Alternative names or surface mentions")


class Relation(BaseModel):
    """Grounded directed relation between entities with exact transcript evidence."""
    subject: str = Field(..., description="Subject entity name")
    predicate: str = Field(..., description="Relation predicate / edge label")
    object: str = Field(..., description="Object entity name")
    quote: str = Field(..., description="Exact quote from transcript (max 25 words)")
    start_sec: float = Field(..., description="Start timestamp in seconds")
    end_sec: float = Field(..., description="End timestamp in seconds")

    @field_validator("end_sec")
    @classmethod
    def validate_time_range(cls, end_val: float, info) -> float:
        start_val = info.data.get("start_sec")
        if start_val is not None and start_val > end_val:
            raise ValueError(f"start_sec ({start_val}) must be <= end_sec ({end_val})")
        return end_val

    @field_validator("quote")
    @classmethod
    def validate_quote_word_count(cls, quote_val: str) -> str:
        words = quote_val.strip().split()
        if len(words) > 25:
            raise ValueError(f"quote exceeds max 25 words (found {len(words)} words)")
        return quote_val


class ChunkExtraction(BaseModel):
    """Extraction output from a transcript chunk."""
    entities: List[Entity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relation_entities_exist(self) -> ChunkExtraction:
        # Build set of valid entity identifiers/names (case-insensitive and alias-aware)
        valid_names = set()
        for ent in self.entities:
            valid_names.add(ent.name.strip().lower())
            for alias in ent.aliases:
                valid_names.add(alias.strip().lower())

        for rel in self.relations:
            subj = rel.subject.strip().lower()
            obj = rel.object.strip().lower()
            if subj not in valid_names:
                raise ValueError(
                    f"Relation subject '{rel.subject}' does not exist in extracted entities."
                )
            if obj not in valid_names:
                raise ValueError(
                    f"Relation object '{rel.object}' does not exist in extracted entities."
                )
        return self


class Chapter(BaseModel):
    """High-level semantic chapter of a video."""
    title: str = Field(..., description="Chapter title")
    start_sec: float = Field(..., description="Start timestamp in seconds")
    summary: str = Field(..., description="Brief summary of the chapter")


# Backwards compatibility aliases
VideoChapter = Chapter
TranscriptChunk = Chunk


class KnowledgeNode(BaseModel):
    id: str
    label: str
    type: str = "Concept"
    description: Optional[str] = ""


class KnowledgeEdge(BaseModel):
    source: str
    target: str
    relation: str
    evidence_quote: str
    start_time: float
    end_time: float
    confidence: float = 1.0


class KnowledgeGraph(BaseModel):
    nodes: List[KnowledgeNode] = Field(default_factory=list)
    edges: List[KnowledgeEdge] = Field(default_factory=list)


class QACitation(BaseModel):
    timestamp_str: str
    start_time: float
    end_time: float
    quote: str
    verified: bool = False
    match_score: float = 0.0


class QAResponse(BaseModel):
    question: str
    answer: str
    citations: List[QACitation] = Field(default_factory=list)
    grounded: bool = True


class VideoAnalysisResult(BaseModel):
    video_id: str
    title: str = "Video Analysis"
    duration: float = 0.0
    summary: str
    transcript: List[Segment] = Field(default_factory=list)
    chapters: List[Chapter] = Field(default_factory=list)
    graph: KnowledgeGraph = Field(default_factory=KnowledgeGraph)
