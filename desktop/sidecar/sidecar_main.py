"""Entry point for the PyInstaller-frozen engine sidecar.

Bundled into desktop/src-tauri/binaries/cutlist-engine-sidecar-<triple>.exe and
spawned by the Tauri shell on 127.0.0.1:8765. Serves only the cutlist_engine
API — the UI itself is the webview app, so no frontend mount is needed.
"""
from __future__ import annotations

import os

# Local desktop app: the engine binds loopback only and must not inherit a
# deployment's API token (which would break the SPA's unauthenticated calls).
os.environ["CUTLIST_NO_DOTENV"] = "1"
os.environ["CUTLIST_API_TOKEN"] = ""

import uvicorn

from cutlist_engine.server import app


def main() -> None:
    port = int(os.environ.get("CUTLIST_PORT", "8765"))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        workers=1,  # session state + locks live in-process
        log_level="info",
    )


if __name__ == "__main__":
    main()
