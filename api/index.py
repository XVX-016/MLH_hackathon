import sys
from pathlib import Path

# Ensure ROOT_DIR is in sys.path so modules like videograph and app can be imported
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
