# videograph

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688.svg)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://docs.pydantic.dev)

**videograph** transforms any video into:
1. **Timestamped Verbatim Transcript** (divided into spoken cue segments)
2. **Chronological Video Chapters & Executive Summary**
3. **Evidence-Grounded Knowledge Graph** (where **EVERY single edge** carries an exact quote, `[MM:SS]` start/end timestamps, and verification confidence)
4. **Grounded Q&A Engine** with `[MM:SS]` citations rigorously verified against the transcript via RapidFuzz + FAISS semantic retrieval.

## Team workflow

This Hacktoberfest build uses a protected three-member workflow: **Hardik** owns
integration and the public contract, **Tanmmay** owns media intelligence, and
**Faariz** owns the evidence explorer. Every coding agent must first receive an
exact name confirmation from one of those members and may edit only that owner's
paths. The complete build order, handoff format, and acceptance criteria are in
[docs/TEAM_WORKFLOW.md](docs/TEAM_WORKFLOW.md); the machine-checkable ownership
map and local gate are in `team/ownership.json` and
`tools/verify_ownership.py`.

---

## Architecture & Package Layout

```
MLH_hackathon/
├── videograph/
│   ├── schemas.py       # Pydantic v2 data models
│   ├── ingest.py        # Video download (yt-dlp) & 16kHz audio extraction (ffmpeg)
│   ├── transcribe.py    # VTT/SRT parsing & Gemini audio transcription
│   ├── chunk.py         # Sliding window transcript chunking
│   ├── prompts.py       # JSON-enforced prompts for LLM extraction
│   ├── extract.py       # Summary, chapter, and edge evidence extraction
│   ├── resolve.py       # Canonical entity deduplication & clustering
│   ├── graph.py         # NetworkX integration & Vis.js network data serialization
│   ├── grounding.py     # Fuzzy & semantic quote verification engine
│   ├── qa.py            # FAISS dense retriever & grounded Q&A
│   ├── llm.py           # Cached Gemini API calls with automatic retry
│   └── cli.py           # Command line runner
├── app/
│   ├── main.py          # FastAPI application server
│   └── static/          # Vis-network + Vanilla JS UI & modern CSS
├── eval/
│   └── evaluate.py      # Grounding rate and citation precision metrics
├── tests/
│   └── test_videograph.py # Full pytest test suite
└── LICENSE              # MIT License
```

---

## Quickstart

### 1. Set Your Environment Key
```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 2. Run the Web Application
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Navigate to `http://localhost:8000` to interact with the dashboard, load the built-in demo sample, or submit any video/audio/subtitles!

### 3. Run via CLI
```bash
# Analyze a video or subtitles file
python -m videograph.cli analyze --input sample.mp4 --output analysis.json

# Grounded Q&A against any transcript
python -m videograph.cli qa --transcript analysis.json --query "What is the key mechanism?"
```

### 4. Run Pytest Suite & Evaluation Harness
```bash
python -m pytest tests/test_videograph.py -v
python -m eval.evaluate
```
