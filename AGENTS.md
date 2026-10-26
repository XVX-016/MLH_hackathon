# VideoGraph team guardrails

This repository is built by three human owners and their scoped coding agents:
**Hardik**, **Tanmmay**, and **Faariz**.  This file is the source of truth for
agent behavior; `docs/TEAM_WORKFLOW.md` contains the complete hand-off plan.

## Open collaboration & permissions

Team members and agents may freely read, edit, generate, and run tasks across
the entire repository without identity gating or ownership locks. Members and agents
do not need to state `I am [name]` to begin work or make changes.

All team members (**Hardik**, **Tanmmay**, and **Faariz**) and agents have full
permission to contribute across all files and components as needed.

## General agent rules

- Keep secrets out of commits; use `.env.example` only for variable names.
- Add tests alongside code and run the test suite to ensure no regressions.
- Keep the codebase clean, modular, and maintainable.

## Project launch & Agent skills

- **Console-guided startup**: Run `python run.py` to start the server. It displays the active port, API documentation URL, offline demo instructions, and key configuration status.
- **Ownership verification**: Run `python tools/verify_ownership.py --member <Name> --base HEAD` before submitting work.
- **Hackathon Agent Skills**: Agents should leverage relevant DevRelay and sponsor skills:
  - `devrelay-sponsor-skills`: For official SDKs and sponsor integrations (e.g. DigitalOcean, Gemini).
  - `devrelay-challenges`: For judging rubrics, prize criteria, and challenge requirements.
  - `devrelay-offers`: For cloud credits and promo codes.
  - `devrelay-mlh-submissions`: For hackathon project submission and challenge entry.
- **Heavy Agentic Lane Delegation**: Faariz is equipped with Codex and Claude plans to handle computationally heavy modules (entity resolution, Vis.js graph topology, RapidFuzz quote verification, FAISS semantic search, and evaluation suites).
