"""Reject a member's changed files when they exceed the agreed team lane."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_FILE = ROOT / "team" / "ownership.json"


def changed_files(base: str) -> list[str]:
    # Comparing the base directly with the working tree includes committed,
    # staged, and unstaged work, so the gate is useful *before* a commit too.
    command = ["git", "diff", "--name-only", base]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not read git diff")
    tracked = {line.replace("\\", "/") for line in result.stdout.splitlines() if line}
    untracked_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if untracked_result.returncode:
        raise RuntimeError(untracked_result.stderr.strip() or "Could not read untracked files")
    untracked = {
        line.replace("\\", "/") for line in untracked_result.stdout.splitlines() if line
    }
    return sorted(tracked | untracked)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--paths", nargs="*", help="Explicit paths; useful before committing.")
    args = parser.parse_args()

    ownership = json.loads(OWNERSHIP_FILE.read_text(encoding="utf-8"))
    if args.member not in ownership:
        parser.error(f"Unknown member {args.member!r}; choose one of: {', '.join(ownership)}")

    files = args.paths or changed_files(args.base)
    allowed = ownership[args.member]
    forbidden = [path for path in files if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)]
    if forbidden:
        print(f"Ownership check failed for {args.member}. Out-of-scope files:", file=sys.stderr)
        print("\n".join(f"  - {path}" for path in forbidden), file=sys.stderr)
        print("Hand off these paths to their owner; do not bypass this gate.", file=sys.stderr)
        return 1

    print(f"Ownership check passed for {args.member}: {len(files)} file(s) within scope.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
