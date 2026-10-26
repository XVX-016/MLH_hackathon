import sys
import importlib
from pathlib import Path

# Ensure project ROOT_DIR is in sys.path so modules like videograph and app can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# The Vercel Python serverless runtime loads this file as a module named 'app'
# (i.e., /var/task/app.py), which shadows the 'app' package directory at
# /var/task/app/. We must remove the stale 'app' entry from sys.modules so that
# `app.main` resolves to the package, not to this file itself.
sys.modules.pop("app", None)

from app.main import app  # noqa: E402
