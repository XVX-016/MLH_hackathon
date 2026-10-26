import sys
from pathlib import Path

# Ensure project root is on sys.path so app/ and videograph/ are importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Vercel loads this file as a module named 'app', which shadows the app/ package.
# Pop it so the subsequent import resolves to the package directory.
sys.modules.pop("app", None)

from app.main import app as _fastapi_app  # noqa: E402

# Vercel's new internal-rewrite behavior forwards requests with the rewritten
# destination path, so FastAPI receives "/api/index" instead of "/".
# This ASGI middleware strips that prefix before the request reaches FastAPI.
_PREFIX = "/api/index"


class _DebugAndStripPrefix:
    """Outermost ASGI middleware that logs scope details and normalizes path."""

    def __init__(self, inner, prefix: str) -> None:
        self._inner = inner
        self._prefix = prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            vercel_headers = {
                k.decode("latin1", errors="replace"): v.decode("latin1", errors="replace")
                for k, v in headers.items()
                if k.lower().startswith(b"x-vercel-") or k.lower() == b"x-matched-path"
            }

            path: str = scope.get("path", "")
            raw_path = scope.get("raw_path")
            root_path = scope.get("root_path")
            qs = scope.get("query_string", b"").decode("latin1", errors="replace")

            new_path = path
            if new_path.startswith(self._prefix):
                new_path = new_path[len(self._prefix):]

            if not new_path or not new_path.startswith("/"):
                new_path = "/" + new_path.lstrip("/")
            if not new_path:
                new_path = "/"

            scope = dict(scope)
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode()

            print(
                f"[ASGI LOG] orig_path={path!r} -> path={new_path!r} | raw_path={raw_path!r} | "
                f"root_path={root_path!r} | qs={qs!r} | vercel_headers={vercel_headers}",
                file=sys.stderr,
                flush=True,
            )

        await self._inner(scope, receive, send)


app = _DebugAndStripPrefix(_fastapi_app, _PREFIX)
