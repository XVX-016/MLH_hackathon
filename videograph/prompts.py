"""Prompt templates for videograph LLM operations.

Each prompt specifies a strict JSON schema for zero-shot parsing.
"""

CHAPTERS_AND_SUMMARY_PROMPT = """
You are an expert video analyst. Given the timestamped transcript of a video, produce:
1. A concise, compelling 2-3 paragraph executive summary of the entire content.
2. A list of chronological chapters covering the video.

Transcript:
{transcript_text}

Return ONLY valid JSON matching this exact structure:
{{
  "summary": "Full summary text here...",
  "chapters": [
    {{
      "title": "Chapter title",
      "start": 0.0,
      "end": 125.0,
      "summary": "Brief summary of this chapter"
    }}
  ]
}}
"""

CHAPTERS_PROMPT = """
Create chronological video chapters from these timestamped chunk gists.
Every `start_sec` MUST exactly equal one of the supplied chunk starts.

Chunk gists:
{chunk_gists}

Return ONLY JSON:
{{"chapters": [{{"title": "...", "start_sec": 0.0, "summary": "..."}}]}}
"""

SUMMARY_PROMPT = """
Write a concise executive summary based only on these video chapters and
timestamped entity gists.

Chapters:
{chapters}

Chunk gists:
{chunk_gists}

Return ONLY JSON:
{{"summary": "..."}}
"""

EXTRACT_GRAPH_PROMPT = """
You are an expert knowledge graph engineer. Analyze the following video transcript chunk.
Extract the key entities (Concepts, Technologies, People, Organizations, Methods) and directed relationships between them.

CRITICAL REQUIREMENT:
EVERY edge MUST carry `evidence_quote` which is an EXACT or virtually exact substring quoted from the transcript, along with `start_time` and `end_time` (in seconds) matching where that evidence occurred in the transcript chunk.
Do not hallucinate edges without proof in the text.

Transcript Chunk (from {chunk_start:.1f}s to {chunk_end:.1f}s):
{chunk_text}

Return ONLY valid JSON matching this exact structure:
{{
  "nodes": [
    {{
      "id": "canonical_identifier_lowercase_underscored",
      "label": "Display Name",
      "type": "Concept",
      "description": "Short 1-sentence context"
    }}
  ],
  "edges": [
    {{
      "source": "source_node_id",
      "target": "target_node_id",
      "relation": "USES | EXPLAINS | IMPROVES | CONTRASTS_WITH | DEPENDS_ON | CRITIQUES | IMPLEMENTS",
      "evidence_quote": "exact quote from transcript here",
      "start_time": {chunk_start:.1f},
      "end_time": {chunk_end:.1f},
      "confidence": 0.95
    }}
  ]
}}
"""

RESOLVE_ENTITIES_PROMPT = """
Given the following list of candidate entity labels extracted from multiple chunks of a video,
group them into canonical clusters where duplicates, synonyms, or casing variations represent the same concept.

Candidate Entities:
{candidates_json}

Return ONLY valid JSON with clusters:
{{
  "clusters": [
    {{
      "canonical_id": "unified_lowercase_id",
      "canonical_label": "Unified Display Name",
      "type": "Concept",
      "aliases": ["alias 1", "alias 2"]
    }}
  ]
}}
"""

GROUNDED_QA_PROMPT = """
You are a factual question-answering assistant for video transcripts.
Answer the user's question using ONLY the provided transcript context snippets.

Every key assertion in your answer must be supported by an exact quote and timestamp from the context.
Include [MM:SS] citation markers right after cited claims.

Context Snippets:
{context_snippets}

User Question:
{question}

Return ONLY valid JSON matching this structure:
{{
  "answer": "Answer containing citations like [02:15]...",
  "citations": [
    {{
      "timestamp_str": "02:15",
      "start_time": 135.0,
      "end_time": 145.0,
      "quote": "exact phrase from snippet"
    }}
  ]
}}
"""
