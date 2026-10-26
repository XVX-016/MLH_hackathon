#!/usr/bin/env python3
"""VideoGraph launcher script.

Starts the FastAPI server with informative console output.
"""

from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch VideoGraph — AI-Powered Video & Media Knowledge Extractor"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code change",
    )
    return parser.parse_args()


def display_welcome_banner(host: str, port: int) -> None:
    display_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    app_url = f"http://{display_host}:{port}"
    docs_url = f"http://{display_host}:{port}/docs"

    has_key = bool(os.getenv("GEMINI_API_KEY"))

    banner = f"""
======================================================================
  🎥 VideoGraph — AI-Powered Video & Media Knowledge Extractor
======================================================================

  🚀 Dashboard URL:     {app_url}
  📖 Interactive Docs:  {docs_url}
  🔑 GEMINI_API_KEY:    {'Configured ✅' if has_key else 'Not set (Offline Demo mode fully active) ⚠️'}

----------------------------------------------------------------------
  🎯 What to do next:
  1. Open your browser and navigate to:
     👉 {app_url}

  2. Try the built-in Offline Demo:
     Click the "Load Demo Sample" button to immediately view
     timestamped chapters, verbatim evidence quotes, and an interactive
     knowledge graph without needing external APIs or downloads.

  3. Upload Your Own Media:
     Drag and drop MP4, MKV, WebM, MP3, WAV, VTT, or SRT files (up to 100 MB).

  4. Ask Grounded Questions:
     Ask questions in the Q&A panel to retrieve verified transcript citations
     with exact [MM:SS] timestamps.

----------------------------------------------------------------------
  Press Ctrl+C at any time to shut down the server.
======================================================================
"""
    print(banner, flush=True)


def main() -> None:
    args = parse_args()

    try:
        import uvicorn
    except ImportError:
        print(
            "ERROR: 'uvicorn' is not installed in the current Python environment.\n"
            "Please install dependencies with: pip install -r requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    display_welcome_banner(args.host, args.port)

    try:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except KeyboardInterrupt:
        print("\n👋 VideoGraph server stopped. Goodbye!", flush=True)


if __name__ == "__main__":
    main()
