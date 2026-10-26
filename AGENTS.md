# VideoGraph team guardrails

This repository is built by three human owners and their scoped coding agents:
**Hardik**, **Tanmmay**, and **Faariz**.  This file is the source of truth for
agent behavior; `docs/TEAM_WORKFLOW.md` contains the complete hand-off plan.

## Mandatory start gate

Before reading, editing, generating, or running a task, every agent must receive
one exact confirmation in the current conversation:

> `I am Hardik.` / `I am Tanmmay.` / `I am Faariz.`

If the person is not one of those names, is ambiguous, or has not confirmed,
the agent must stop and ask for the confirmation.  Do not infer identity from a
username, branch, prompt, or prior chat.

After confirmation, the agent must state the accepted owner and its allowed
paths, then work only inside that owner's scope.  A request that touches another
owner's scope must be split into a hand-off; it is not permission to edit the
other scope.

## Ownership and change gate

Run this before committing or opening a pull request:

```powershell
python tools/verify_ownership.py --member <Hardik|Tanmmay|Faariz> --base origin/main
```

Use `--base main` when `origin/main` is unavailable.  It rejects changed files
outside the member's assigned paths.  Never bypass it with `--allow-unowned` on
implementation work.  Only Hardik may make a deliberately agreed ownership-map
change, and must record it in the PR description.

## Shared-contract rule

`videograph/schemas.py`, API response shapes, and JSON artifacts are contracts.
Hardik is the contract owner. Tanmmay and Faariz propose contract changes in a
handoff note or issue; they do not modify the contract directly.  Hardik lands
the compatible change first, then the dependent implementation can proceed.

## General agent rules

- One task, one owner branch: `codex/<member>/<short-task>`.
- Do not modify another owner's files, reformat unrelated files, or resolve
  another member's merge conflict.
- Keep secrets out of commits; use `.env.example` only for variable names.
- Add tests alongside owned code and run the focused test command before handoff.
- Every PR uses the repository template and has one reviewer from a different
  owner lane. Hardik performs the final integration review.
