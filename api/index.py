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


class _StripPrefix:
    """Minimal ASGI middleware that removes a fixed path prefix."""

    def __init__(self, inner, prefix: str) -> None:
        self._inner = inner
        self._prefix = prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") in ("http", "websocket"):
            path: str = scope.get("path", "")
            if path.startswith(self._prefix):
                scope = dict(scope)
                scope["path"] = path[len(self._prefix):] or "/"
                scope["raw_path"] = scope["path"].encode()
        await self._inner(scope, receive, send)


app = _StripPrefix(_fastapi_app, _PREFIX)
