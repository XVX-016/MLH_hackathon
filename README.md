# videograph

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688.svg)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://docs.pydantic.dev)

**videograph** transforms any video into:
1. **Timestamped Verbatim Transcript** (divided into spoken cue segments)
2. **Chronological Video Chapters & Executive Summary**
3. **Interactive Study Flashcards** (grounded with verbatim quotes and `[MM:SS]` video timestamps)
4. **Evidence-Grounded Knowledge Graph** (where **EVERY single edge** carries an exact quote, `[MM:SS]` start/end timestamps, and verification confidence)
5. **Grounded Q&A Engine** with `[MM:SS]` citations rigorously verified against the transcript via RapidFuzz + FAISS semantic retrieval.

## Frontend Experience & Minimalist UI Flow

VideoGraph is designed with a professional, distraction-free aesthetic featuring a sleek dark theme with a subtle geometric SVG grid background and glassmorphism elements:

1. **Minimalist Initial State (Hero Ingestion)**:
   - On initial load, the interface is completely clean and minimalist: only the brand identity and a prominent, centered **YouTube Link Input Bar** (with quick-access pills for "Load Demo Sample" and file upload).
   - Subtle animated SVG grid / ambient glow elements in the background give it an ultra-modern, professional engineering look.
   - Upon submitting a YouTube link, VideoGraph immediately fetches the video details (Title, Duration, Channel) and displays an active pulse processing indicator with step-by-step progress status.

2. **Transition to 3-Tab Results View**:
   - Once processing is complete, the dashboard transitions into the full results view with the **Video Title prominently displayed on top**.
   - The knowledge extraction is neatly divided across **three dedicated tabs**:
     - 📑 **Summary**: Executive summary, key takeaways, and chronological video chapters with `[MM:SS]` timestamp jump links.
     - 🗂️ **Flashcards**: Interactive 3D flip cards for rapid learning—conceptual questions on front, concise grounded answers, supporting verbatim quotes, and clickable timestamps on back.
     - 🕸️ **Graph**: Interactive Vis.js knowledge graph topology mapping concepts, entities, and verified relationships with edge inspection drawer.
3. **Grounded Q&A Drawer**:
   - Accessible from any tab to query the video with verified `[MM:SS]` timestamp citations.

## Team workflow & Agent Division

This Hacktoberfest build is divided among three human owners with scoped coding agent workflows:

- **Hardik** *(Lead & Integration)*: Owns the API contracts (`videograph/schemas.py`: adding `Flashcard` model & response shapes), FastAPI endpoints (`app/main.py`), CLI (`videograph/cli.py`), Docker/deployment, offline demo pipeline, and repo integrity checks.
- **Tanmmay** *(Media Intelligence)*: Owns video/audio ingestion (`yt-dlp`), YouTube metadata fetching, 16kHz audio conversion (`ffmpeg`), VTT/SRT parsing, chunking, and structured LLM extraction for chapters, summary, and **study flashcards**.
- **Faariz** *(Evidence Explorer & Heavy Agentic Lane — Codex / Claude)*: Takes on the heavy reasoning, algorithmic, and visual interface workloads:
  - **Frontend 3-Tab Architecture** (`app/static/**`): Builds the YouTube input bar, video title header, and 3 tab views (**Summary** | **Flashcards** | **Graph**) with responsive design and flip animations.
  - **Entity Resolution & Knowledge Graph** (`videograph/resolve.py`, `videograph/graph.py`): Entity clustering, deduplication, and NetworkX / Vis.js network serialization.
  - **Evidence Grounding Engine** (`videograph/grounding.py`): RapidFuzz + N-gram fuzzy quote alignment, timestamp boundary verification, and confidence scoring.
  - **Semantic Retrieval & Grounded Q&A** (`videograph/qa.py`): Dense vector retrieval (FAISS), hybrid search, and citation verification.
  - **Evaluation & Benchmarking** (`eval/**`): Automated citation precision, recall, and hallucination scoring against ground-truth datasets.

### Mandatory Agent Start Gate

Before any coding agent generates or edits code, the human operator must send the exact confirmation phrase in the conversation:
- `I am Hardik.`
- `I am Tanmmay.`
- `I am Faariz.`

Agents must strictly operate within their assigned file paths defined in [`team/ownership.json`](team/ownership.json). Before submitting a PR or handoff, verify ownership with:
```powershell
python tools/verify_ownership.py --member <Hardik|Tanmmay|Faariz> --base HEAD
```
For detailed handoff contracts and sequence, see [docs/TEAM_WORKFLOW.md](docs/TEAM_WORKFLOW.md).

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

### 1. Set Your Environment Key (Optional for Demo)
```bash
export GEMINI_API_KEY="your-gemini-api-key"
```
*(Note: Not required for the offline demo. The built-in demo runs with zero external API calls or keys.)*

### 2. Run the Application
Launch the server with the console-guided startup script:
```bash
python run.py
```
This startup script automatically:
- Checks environment requirements and key configurations.
- Displays the exact port (`http://localhost:8000`) and interactive Swagger docs URL (`/docs`).
- Outlines immediate actions (loading the offline demo, testing uploads, running verified Q&A).
- Supports flags: `python run.py --host 0.0.0.0 --port 8000 --reload`.

Alternatively, run directly via Uvicorn:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Navigate to `http://localhost:8000` to interact with the dashboard:
- The **Load Demo Sample** button works offline and demonstrates the complete evidence path: chapters, transcript, grounded graph edges, and timestamp-linked answers.
- Real uploads support MP4, MKV, WebM, MP3, WAV, VTT, and SRT files up to 100 MB. URL ingestion will be enabled once Tanmmay's lane delivers the media download pipeline.

---

## Agent Skills & Team Capabilities

VideoGraph integrates with developer agent skills and protocols to accelerate hackathon delivery:

- **Launch & Startup Assistant**: `python run.py` provides immediate status, port inspection, and quick-start checklists for agents and human operators.
- **Ownership Verification Skill / Tool**: `python tools/verify_ownership.py --member <Name> --base HEAD` enforces strict file boundaries and prevents cross-member merge conflicts.
- **Sponsor & Cloud Agent Skills**:
  - `devrelay-sponsor-skills`: Official skills for integrating sponsor services (e.g. DigitalOcean App Platform, Gemini inference).
  - `devrelay-challenges`: Querying event criteria, deadlines, and prize rubrics.
  - `devrelay-offers`: Managing hackathon credits and sponsor tooling perks.
  - `devrelay-mlh-submissions`: Managing project submissions, demos, and challenge entries.
- **Multi-Agent Lane Delegation**:
  - **Hardik**: Public contract enforcement, FastAPI integration, startup tooling, and repo governance.
  - **Tanmmay**: Audio/video ingestion, media normalizers, and LLM chapter extraction.
  - **Faariz (Codex / Claude Heavy Agentic Lane)**: High-capacity multi-agent execution for entity clustering, NetworkX/Vis.js graph topology, RapidFuzz quote verification, FAISS semantic search, and evaluation suites.

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
