# VideoGraph: three-member delivery workflow

## Product target

VideoGraph converts a short video, audio file, subtitles, or video URL into a
timestamped transcript, useful chapters and takeaways, evidence-grounded graph
facts, and answers that link back to the exact source moment.  The demo must
make one complete path visible: **input → processing → chapter/takeaway view →
question → clickable timestamped evidence**.

This plan maps directly to the existing codebase. It avoids a rewrite during a
hackathon and protects the two important claims in the README: evidence is
verbatim and every answer is timestamp-cited.

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
| **Hardik** (lead/integration) | Own the public product contract: FastAPI endpoints, request validation, job/result loading, CLI integration, demo flow, Docker/CI, README, final demo and submission package. Land contract changes before dependent work. | `app/main.py`, `videograph/schemas.py`, `videograph/cli.py`, `videograph/__init__.py`, `README.md`, `Dockerfile`, `.github/`, `.env.example`, `requirements.txt`, `docs/`, `team/`, `tools/`, `tests/test_integration.py` | `pytest tests/ -v`; launch Uvicorn; manually complete the demo path; verify no key is logged. |
| **Tanmmay** (media intelligence) | Make input reliable: URL/file/subtitle intake, audio extraction, VTT/SRT parsing, timestamp normalization, chunking, structured LLM chapter/takeaway extraction, retries/cache. Provide deterministic fixtures for integration. | `videograph/ingest.py`, `videograph/transcribe.py`, `videograph/chunk.py`, `videograph/prompts.py`, `videograph/extract.py`, `videograph/llm.py`, `tests/test_pipeline.py` | Focused pipeline tests, including malformed subtitle and an LLM-failure/retry case; sample artifact and concise handoff schema. |
| **Faariz** (evidence explorer) | Make knowledge navigable and trustworthy: entity resolution, graph serialization, quote grounding, semantic retrieval/Q&A, evaluation metrics, and the chapter/answer/evidence UI. | `videograph/resolve.py`, `videograph/graph.py`, `videograph/grounding.py`, `videograph/qa.py`, `eval/`, `app/static/`, `tests/test_explorer.py` | Retrieval/grounding tests; evaluation report showing citation precision; browser check that a result opens the correct timestamp. |

`tests/test_videograph.py` is the existing shared baseline. Do not casually edit
it during parallel work; Hardik merges agreed changes or moves coverage into the
owner-specific test files.

## Build sequence and dependency gates

1. **Hardik — establish the demo contract.** Freeze one `AnalysisResult` JSON
   fixture, endpoint request/response shapes, file-size/duration limits, error
   format, and definition of a valid timestamp citation. Create a runnable
   no-key demo path before live-model work.
2. **Tanmmay — deliver ingestion to extraction.** Work only against the frozen
   contract. Emit a valid artifact even where optional graph fields are empty.
   Hand off fixture, command, known limits, and test output.
3. **Faariz — deliver evidence and interface.** Consume the fixture, preserve
   source segment IDs/times through every transform, and make each citation
   clickable. Return a tested result artifact and UI behavior notes.
4. **Hardik — integrate and harden.** Merge lanes in dependency order,
   wire endpoint-to-UI behavior, add integration tests, remove regressions, and
   prepare the README, architecture diagram, screenshots, live demo, and video.
5. **All three — review and submit.** Tanmmay reviews the input/error path;
   Faariz reviews evidence accuracy/UI; Hardik validates the complete journey
   and owns the final submission checklist.

No lane begins a dependent feature until its preceding handoff is accepted. A
contract disagreement is a Hardik decision; record it in the PR or issue before
code changes.

## Definition of done

- A reviewer can run the app from a fresh checkout using only documented setup.
- One supplied video/subtitle input shows chapters and takeaways.
- A question returns a concise answer with a quote and `[MM:SS]` range that
  maps to actual transcript text.
- Broken URL, malformed subtitles, unsupported media, unavailable API key, and
  model failure produce actionable errors rather than a false answer.
- No credentials, uploaded media, or raw private transcript are committed.
- `pytest tests/ -v` and `python -m eval.evaluate` pass; the demo is recorded
  against the same revision being submitted.

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

## Suggested issue cards

1. Hardik: freeze contract and offline demo artifact.
2. Tanmmay: subtitle/file/URL ingestion with normalized transcript.
3. Tanmmay: chapters and takeaways with guarded LLM output.
4. Faariz: quote verifier and cited retrieval.
5. Faariz: explorer dashboard with deep-linked timestamps.
6. Hardik: end-to-end endpoint, Docker, evaluation, demo and submission assets.
