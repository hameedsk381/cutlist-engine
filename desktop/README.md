# CutList Engine — Desktop App (Tauri 2)

Native Windows desktop wrapper for the cutlist engine:

- **UI** — the existing React review SPA (`../frontend`) runs in the webview
- **Engine** — the Python FastAPI engine is bundled as a PyInstaller sidecar
  and spawned by the Rust shell on `127.0.0.1:8765`
- Result: one ~15–25 MB installer, no Python required on the user's machine

```
┌─────────────────────────────────────────────┐
│  Tauri 2 shell (Rust)                       │
│  ┌───────────────────────────────────────┐  │
│  │  React review SPA (webview)           │  │
│  └──────────────┬────────────────────────┘  │
│                 │ http://127.0.0.1:8765     │
│  ┌──────────────▼────────────────────────┐  │
│  │  cutlist-engine sidecar (.exe)        │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## One-time prerequisites

1. **Rust + MSVC toolchain** — install from <https://rustup.rs>
   (accepts the Visual Studio C++ Build Tools prompt), or:
   `winget install Rustlang.Rustup`
2. **Python 3.11+** with the repo installed: `python -m pip install -e .`
3. Node 20+ (already required by the frontend)

## Development

```bash
cd desktop
npm install              # @tauri-apps/cli
npm run dev              # builds sidecar? no — see below; launches webview + vite
```

For `npm run dev` you don't need the frozen sidecar: the shell expects the
engine at `binaries/…`. For a quick dev loop run the engine directly:

```bash
# terminal 1 — engine
python desktop/sidecar/sidecar_main.py

# terminal 2 — UI + shell (skip sidecar spawn errors, engine is already up)
npm run dev
```

If the sidecar binary is present it is spawned automatically.

## Production build

```bash
cd desktop
npm install
npm run sidecar:build    # PyInstaller → src-tauri/binaries/*.exe
npm run build            # tauri build → NSIS installer
```

Installer output: `src-tauri/target/release/bundle/nsis/CutList Engine_0.1.0_x64-setup.exe`

## Files

| Path | Purpose |
|---|---|
| `src-tauri/src/main.rs` | Spawns/kills the engine sidecar, holds the window |
| `src-tauri/tauri.conf.json` | Window, bundle, NSIS, externalBin config |
| `src-tauri/capabilities/default.json` | Tauri 2 permission manifest |
| `sidecar/sidecar_main.py` | Frozen-engine entry (uvicorn on 127.0.0.1:8765) |
| `sidecar/build_sidecar.ps1` | PyInstaller packaging → `binaries/` |
| `sidecar/gen_icons.py` | Regenerates app icons (`py -3 desktop/sidecar/gen_icons.py`) |

## How the SPA talks to the engine

`frontend/src/api.ts` detects Tauri (`__TAURI_INTERNALS__`) and sets
`baseURL = http://127.0.0.1:8765`; in the browser it stays same-origin.
CORS is already open (`allow_origins=["*"]`) in `server.py`, and the sidecar
binds to loopback only. The API token is **not** used in the desktop app —
the engine only listens on localhost.

## Notes / roadmap

- NSIS installer embeds the WebView2 bootstrapper (Win10 without WebView2 works).
- macOS/Linux builds: add matching `externalBin` triple builds in
  `build_sidecar.ps1` equivalents; `targets` in `tauri.conf.json` accordingly.
- Auto-update: add `tauri-plugin-updater` when you have a release feed.
