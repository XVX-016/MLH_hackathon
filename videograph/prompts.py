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

Return ONLY valid JSON matching this exact structure:
{{"chapters": [{{"title": "Concise Title Here", "start_sec": 0.0, "summary": "One sentence summary."}}]}}
"""

SUMMARY_PROMPT = """
Write a short summary of this video based only on these chapters and timestamped gists.

- First sentence: the video's main point or answer in at most 25 words, stated directly.
  It is shown on its own as a headline, so never start with "This video", "In this video", or "The speaker".
- Then 2-3 sentences on how the video supports that point.
- End with one sentence on the practical takeaway or the main limitation.
- Use only facts present in the chapters and gists.

Chapters:
{chapters}

Chunk gists:
{chunk_gists}

Return ONLY JSON:
{{"summary": "..."}}
"""

EXTRACT_GRAPH_PROMPT = """
You are an expert knowledge graph engineer. Analyze the following video transcript chunk.
Extract key entities (Concepts, Technologies, People, Organizations, Methods) and directed relationships between them.

CRITICAL REQUIREMENTS:
- EVERY edge MUST carry `evidence_quote`: one contiguous passage copied character for character from the transcript.
  Do not paraphrase, fix grammar, or join separate passages with "..." - pick the single passage that states the relation.
- `start_time` and `end_time` are the timestamps of the transcript line(s) that contain that exact passage.
- `relation` is a short, specific verb phrase in lowercase taken from what is said, e.g. "announces", "priced at",
  "powered by", "replaces", "competes with", "is set in". Never use vague predicates such as "uses", "is", "has",
  "implements", or "related to".
- Do not create an edge unless the quote itself states the relationship.

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
      "relation": "specific verb phrase, e.g. priced at",
      "evidence_quote": "exact quote from transcript here",
      "start_time": {chunk_start:.1f},
      "end_time": {chunk_end:.1f},
      "confidence": 0.95
    }}
  ]
}}
"""

EXTRACTION_PROMPT = """
Extract a compact, evidence-grounded knowledge representation from this timestamped transcript chunk.
Return only facts explicitly supported by an exact verbatim quote copied from the chunk.

Rules:
1. Every quote MUST be an exact verbatim substring from the transcript text (max 25 words). Never paraphrase.
2. Predicates should be specific informative verbs ("announces", "priced at", "powered by", "replaces", "implements", "controls", "improves", "contrasts with"). Avoid generic "uses", "is", "has".

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
      "predicate": "implements",
      "object": "Entity name or alias",
      "quote": "exact verbatim transcript quote",
      "start_sec": {chunk_start:.1f},
      "end_sec": {chunk_end:.1f}
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
- A clear question on the front that stands on its own: a reader who has not seen the video must
  understand it. Never write "mentioned in the transcript", "in the video", "the speaker says", or
  similar; ask about the subject itself (e.g. "What is the starting price of the Apple TV 4K?").
- A concise answer on the back, written as a self-contained statement of the fact or conclusion.
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
      "question": "What is the primary function of...?",
      "answer": "Concise grounded answer here.",
      "key_quote": "exact verbatim phrase from transcript",
      "start_sec": {chunk_start:.1f},
      "end_sec": {chunk_end:.1f}
    }}
  ]
}}
"""
