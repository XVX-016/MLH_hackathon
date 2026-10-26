# seekwise: three-member delivery workflow

## Product target & UX Flow

seekwise (Python package: `videograph`) converts any video, audio file, subtitles, or YouTube URL into an
interactive, evidence-grounded study companion:

1. **Minimalist Initial State**: The user sees a distraction-free hero layout with an
   ambient SVG grid / dark background and a single centered YouTube link input bar
   (plus quick pill buttons for the 1-click offline demo and file upload).
2. **Metadata Fetch & Processing**: Upon submitting, seekwise fetches video details
   (Title, Duration, Channel) and enters a visual progress state.
3. **Interactive 3-Tab Presentation**: Once processing finishes, the interface
   smoothly transitions to display the **Video Title** prominently on top and renders
   three dedicated tabs:
   - 📑 **Summary**: Executive overview, chronological chapters, and key takeaways.
   - 🗂️ **Flashcards**: Interactive study cards with question prompts on front, and
     concise answers, supporting verbatim quotes, and `[MM:SS]` jump links on back.
   - 🕸️ **Graph**: Interactive Vis.js knowledge graph topology mapping concepts,
     technologies, and verified relationships with evidence inspection modals.
4. **Verified Q&A**: Users can query the transcript at any time and receive answers
   strictly grounded with clickable `[MM:SS]` timestamp citations.

## Non-negotiable agent launch protocol

No coding agent may begin until the human operator answers with their exact
member name: `Hardik`, `Tanmmay`, or `Faariz`. The agent then replies:

> Confirmed: I am working for **<name>**. I will change only **<owned paths>**
> and will hand off all other work.

The agent must read `AGENTS.md`, run the ownership check before handoff, and
stop on an out-of-scope request. A named person can delegate execution to an
agent, but the owner remains accountable for review and handoff.

## Work lanes

| Owner | Mission and deliverable | Exclusive paths | Required proof before handoff |
| --- | --- | --- | --- |
| **Hardik** (lead/integration) | Own the public product contract: FastAPI endpoints, request validation, job/result loading, `Flashcard` schema and serialization, CLI integration, demo flow, Docker/CI, README, final demo and submission package. Land contract changes before dependent work. | `app/main.py`, `videograph/schemas.py`, `videograph/cli.py`, `videograph/__init__.py`, `README.md`, `Dockerfile`, `.github/`, `.env.example`, `.gitignore`, `requirements.txt`, `docs/`, `team/`, `tools/`, `data/demo/`, `tests/test_integration.py`, `run.py` | `pytest tests/ -v`; launch `python run.py`; verify offline demo loads chapters, flashcards, and graph without external APIs. |
| **Tanmmay** (media intelligence) | Make input reliable: YouTube URL metadata fetching (`yt-dlp`), audio extraction (`ffmpeg`), VTT/SRT parsing, timestamp normalization, chunking, structured LLM extraction for chapters, summary, and **study flashcards**. | `videograph/ingest.py`, `videograph/transcribe.py`, `videograph/chunk.py`, `videograph/prompts.py`, `videograph/extract.py`, `videograph/llm.py`, `tests/test_pipeline.py` | Focused pipeline tests including YouTube metadata fetch, malformed subtitle and LLM-failure/retry cases; sample artifact with chapters and flashcards. |
| **Faariz** (evidence explorer & heavy agentic lane: Codex / Claude) | **Heavy Agentic Lane**: Multi-agent implementation of: <br>1. **Frontend Minimalist UI & 3-Tab Architecture** (`app/static/**`): Sleek dark theme with an ambient geometric SVG grid background. Initially displays only the centered hero YouTube input bar (with demo/upload pill buttons), then seamlessly transitions to the video title header and 3 interactive tabs (**Summary** \| **Flashcards** \| **Graph**) with 3D card flip animation and `[MM:SS]` video scrubber seeking.<br>2. **Graph & Grounding**: Entity resolution (`resolve.py`), NetworkX/Vis.js graph topology (`graph.py`), and RapidFuzz quote verification (`grounding.py`).<br>3. **Dense Retrieval**: FAISS dense vector search and verified Q&A citations (`qa.py`).<br>4. **Evaluation**: Automated evaluation suite (`eval/**`). | `videograph/resolve.py`, `videograph/graph.py`, `videograph/grounding.py`, `videograph/qa.py`, `eval/**`, `app/static/**`, `tests/test_graph.py`, `tests/test_grounding.py`, `tests/test_qa.py`, `tests/test_resolve.py`, `tests/test_explorer.py` | Focused retrieval/grounding tests; automated evaluation report showing citation precision `1.0`; browser verification of minimalist SVG grid UI, 3-tab layout, flashcard flip interaction, and graph rendering. |

`tests/test_videograph.py` is the existing shared baseline. Do not casually edit
it during parallel work; Hardik merges agreed changes or moves coverage into the
owner-specific test files.

## Current parallel delivery board

The current integration contract is a job API: `POST /process`, `POST /api/analyze/url`,
`GET /status/{id}`, `GET /result/{id}`, and `POST /ask`.  A checked-in JSON demo in
`data/demo/` loads on server startup with zero external model calls.

| Owner | Status & Delivered | Active Task & Acceptance |
| --- | --- | --- |
| **Hardik** *(Lead/Integration)* | ✅ **Delivered**: `Flashcard` schema, offline demo artifact (`demo_attention.json`), FastAPI `lifespan` handler, CLI runner with `--demo` flag, console-guided launcher (`run.py`), YouTube URL ingestion wired into `app/main.py` with multi-tier fallback chain & `NeedsUpload` error handling, upload limit validation & temp file cleanup, and full integration test coverage. | ✅ **Complete**: Public contract frozen, all endpoints live, 100% integration tests passing. Ready for final submission integration. |
| **Tanmmay** *(Media Intelligence)* | ✅ **Delivered (PR #3 Merged)**: `fetch_youtube_metadata`, `download_youtube_audio`, `FLASHCARDS_PROMPT`, and `generate_flashcards` with 110 lines of unit tests in `tests/test_pipeline.py`. | ⏳ **Active Task**: Verify live Gemini / Whisper audio transcription resilience on diverse audio accents and edge-case subtitle encodings. |
| **Faariz** *(Heavy Agentic Lane — Codex / Claude)* | ✅ **Delivered**: Entity clustering algorithms, NetworkX graph serialization, RapidFuzz verification, and citation precision harness. | ⏳ **Active Task**: Complete the minimalist frontend redesign in [`app/static/**`](../app/static/):<br>1. **Hero State**: Dark minimalist layout with ambient geometric SVG grid background and centered YouTube input bar (with offline demo / file upload pill triggers).<br>2. **Processing State**: Fetched video metadata card (Title, Duration, Channel) with progress pulse indicator.<br>3. **Results State**: Video title header + 3 interactive tabs (**Summary** \| **Flashcards** with 3D flip animation \| **Graph** with Vis.js network).<br>4. **Deep-Linking**: Timestamp seek handlers syncing audio/video cues. |

These lanes are intentionally independent: Tanmmay emits validated transcript
and extraction artifacts, Faariz consumes the frozen result JSON, and Hardik
alone merges public-contract changes. Do not edit another lane merely to make a
local test pass; record the required contract change in the handoff instead.

## Build sequence and dependency gates

1. **Hardik — establish the demo contract (Complete ✅).** Freezes `AnalysisResult` and
   `Flashcard` schemas, request/response shapes, file-size/duration limits, error
   format, and definition of a valid timestamp citation.
2. **Tanmmay — deliver media & extraction pipeline (Complete ✅).** Delivered YouTube
   metadata/audio ingestion and LLM flashcard generation against the contract.
3. **Hardik — connect live URL endpoints (Active ⏳).** Wire `POST /api/analyze/url` to
   Tanmmay's media downloader, orchestrating background jobs.
4. **Faariz — deliver minimalist UI and 3-tab explorer (Active ⏳).** Implement the SVG
   grid dark theme, YouTube hero input, 3D flip flashcards, and Vis.js knowledge graph.
5. **Hardik — final hardening and submission review.** Verify complete end-to-end journey,
   run full test suite and evaluation harness, verify ownership, and prepare demo video.

## Definition of done

- A reviewer can run `python run.py` from a fresh checkout using only documented setup.
- Pasting a YouTube link or uploading media loads video title, summary, chapters, flashcards, and graph.
- Clicking any timestamp or flashcard quote jumps to the exact moment in the video.
- Grounded Q&A returns concise answers with quotes and `[MM:SS]` ranges verified against the transcript.
- Broken URL, malformed subtitles, unsupported media, and model failures produce actionable errors.
- No credentials or raw private transcripts are committed.
- `pytest tests/ -v` (56+ passed) and `python -m eval.evaluate` pass with precision `1.0`.

## Handoff template

Every lane ends with this compact note in the PR or issue:

```text
Owner confirmed: <name>
Scope changed: <files>
Contract consumed/produced: <schema or artifact version>
Commands run: <commands and result>
Known limitations: <none or list>
Next owner and unblock condition: <name + exact action>
```

## Mandatory Agent Start Gate & Ownership Rules

Before any coding agent generates or edits code, the human operator must send the exact confirmation phrase in the conversation:
- `I am Hardik.`
- `I am Tanmmay.`
- `I am Faariz.`

Agents must strictly operate within their assigned file paths defined in [`team/ownership.json`](../team/ownership.json). Before submitting a PR or handoff, verify ownership with:
```powershell
python tools/verify_ownership.py --member <Hardik|Tanmmay|Faariz> --base main
```

## Agent Skills & Hackathon Accelerators

seekwise integrates with developer agent skills and protocols to accelerate delivery:
- **Console Launcher**: `python run.py` provides immediate status, port inspection, and quick-start checklists.
- **Ownership Verification Skill**: `python tools/verify_ownership.py --member <Name> --base HEAD` enforces strict file boundaries.
- **Sponsor & Cloud Agent Skills**:
  - `devrelay-sponsor-skills`: For integrating sponsor services (e.g. Gemini inference).
  - `devrelay-challenges`: Querying event criteria, deadlines, and prize rubrics.
  - `devrelay-offers`: Managing hackathon credits and sponsor tooling perks.
  - `devrelay-mlh-submissions`: Managing project submissions, demos, and challenge entries.
- **Heavy Agentic Lane Delegation**: Faariz is equipped with Codex and Claude plans to handle computationally heavy modules (entity resolution, Vis.js graph topology, RapidFuzz quote verification, FAISS semantic search, and evaluation suites).

