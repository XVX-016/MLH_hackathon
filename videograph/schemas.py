"""Data schemas for videograph.

All structures use Pydantic v2 with strict validation and clean serialization.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """Single timed segment of transcribed video/audio."""
    id: int = Field(..., description="0-indexed segment sequence number")
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    text: str = Field(..., description="Transcript speech content")

    @property
    def timestamp_str(self) -> str:
        """Formatted [MM:SS] start timestamp."""
        m = int(self.start // 60)
        s = int(self.start % 60)
        return f"{m:02d}:{s:02d}"


class VideoChapter(BaseModel):
    """High-level semantic chapter of a video."""
    title: str = Field(..., description="Chapter title")
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    summary: str = Field(..., description="Brief 1-2 sentence overview of the chapter")


class KnowledgeNode(BaseModel):
    """Node in the video knowledge graph."""
    id: str = Field(..., description="Unique canonical entity identifier")
    label: str = Field(..., description="Human readable entity name")
    type: str = Field(default="Concept", description="Entity category: Concept, Person, Tech, Tool, Organization, etc.")
    description: Optional[str] = Field(default="", description="Short context description")


class KnowledgeEdge(BaseModel):
    """Directed edge in the knowledge graph carrying strict grounding evidence."""
    source: str = Field(..., description="Source node id")
    target: str = Field(..., description="Target node id")
    relation: str = Field(..., description="Predicate relation (e.g., USES, CRITIQUES, EXPLAINS, CONTRASTS_WITH)")
    evidence_quote: str = Field(..., description="Exact or near-exact quote from the transcript proving this relation")
    start_time: float = Field(..., description="Start timestamp in seconds where evidence occurs")
    end_time: float = Field(..., description="End timestamp in seconds where evidence occurs")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from extraction/verification")


class KnowledgeGraph(BaseModel):
    """Complete knowledge graph structure."""
    nodes: List[KnowledgeNode] = Field(default_factory=list)
    edges: List[KnowledgeEdge] = Field(default_factory=list)


class QACitation(BaseModel):
    """Citation pointing to transcript evidence verified by fuzzy/embedding match."""
    timestamp_str: str = Field(..., description="[MM:SS] format")
    start_time: float = Field(..., description="Start seconds")
    end_time: float = Field(..., description="End seconds")
    quote: str = Field(..., description="Exact phrase from transcript")
    verified: bool = Field(default=False, description="Whether quote was verified against transcript text")
    match_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Verification match score (0-100)")


class QAResponse(BaseModel):
    """Answer to user question with verified transcript grounding."""
    question: str
    answer: str
    citations: List[QACitation] = Field(default_factory=list)
    grounded: bool = Field(default=True, description="True if citations back the core claims")


class VideoAnalysisResult(BaseModel):
    """Full analysis output for a processed video."""
    video_id: str
    title: str = "Video Analysis"
    duration: float = 0.0
    summary: str
    transcript: List[TranscriptSegment] = Field(default_factory=list)
    chapters: List[VideoChapter] = Field(default_factory=list)
    graph: KnowledgeGraph = Field(default_factory=KnowledgeGraph)
