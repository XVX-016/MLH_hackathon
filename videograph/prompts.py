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
Create chronological chapters for this video from the timestamped chunk gists.

Rules:
- 5 to 10 chapters (fewer only if there are fewer chunks), covering the whole video in order.
- Every `start_sec` must equal one of the supplied chunk starts, and starts must strictly increase.
- Titles: under 6 words, specific to what is said (no "Introduction", "Part 2", or entity lists).
- Summary: exactly one sentence saying what this part covers, based only on the gists.

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

EXTRACTION_PROMPT = """
Extract a compact, evidence-grounded knowledge representation from this
timestamped transcript chunk. Return only facts explicitly supported by an
exact quote in the chunk.

Chunk start: {chunk_start:.1f}
Chunk end: {chunk_end:.1f}
Transcript:
{chunk_text}

Return ONLY valid JSON matching this structure:
{{
  "entities": [
    {{"name": "Entity name", "type": "Concept", "aliases": ["optional alias"]}}
  ],
  "relations": [
    {{
      "subject": "Entity name or alias",
      "predicate": "USES",
      "object": "Entity name or alias",
      "quote": "exact transcript quote of at most 25 words",
      "start_sec": 0.0,
      "end_sec": 5.0
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

FLASHCARDS_PROMPT = """
You are an expert educator creating study flashcards from a video transcript chunk.
For each key concept or claim in the chunk, produce one flashcard with:
- A clear conceptual question on the front.
- A concise, grounded answer on the back.
- An exact verbatim quote from the chunk supporting the answer (max 25 words).
- The start and end timestamps (seconds) of the supporting quote.

Every key_quote MUST be an exact substring from the transcript text below.
Do NOT fabricate quotes or timestamps.

Transcript Chunk (from {chunk_start:.1f}s to {chunk_end:.1f}s):
{chunk_text}

Return ONLY valid JSON matching this structure:
{{
  "flashcards": [
    {{
      "id": 0,
      "question": "What is the purpose of...?",
      "answer": "Concise grounded answer here.",
      "key_quote": "exact verbatim phrase from transcript",
      "start_sec": {chunk_start:.1f},
      "end_sec": {chunk_end:.1f}
    }}
  ]
}}
"""
