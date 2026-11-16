//! CutList Engine desktop shell.
//!
//! The React review SPA runs inside the webview; the Python engine
//! (cutlist_engine FastAPI) runs as a bundled sidecar process on
//! 127.0.0.1:8765. The SPA detects Tauri and routes its API calls there
//! (see frontend/src/api.ts).
use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandEvent, CommandChild};
use tauri_plugin_shell::ShellExt;

/// Holds the running engine process so we can kill it on exit.
struct EngineChild(Mutex<Option<CommandChild>>);

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(EngineChild(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let sidecar = handle
                    .shell()
                    .sidecar("cutlist-engine-sidecar")
                    .expect("failed to resolve engine sidecar binary");
                match sidecar.spawn() {
                    Ok((mut rx, child)) => {
                        *handle
                            .state::<EngineChild>()
                            .0
                            .lock()
                            .expect("engine state poisoned") = Some(child);
                        while let Some(event) = rx.recv().await {
                            if let CommandEvent::Stderr(line) = event {
                                eprintln!("[engine] {line}");
                            }
                        }
                    }
                    Err(err) => {
                        eprintln!("failed to start engine sidecar: {err}");
                    }
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            match event {
                // Engine talks to 127.0.0.1 only; keep the process with the window.
                RunEvent::Exit | RunEvent::ExitRequested { .. } => {
                    if let Some(child) =
                        app.state::<EngineChild>().0.lock().expect("engine state poisoned").take()
                    {
                        let _ = child.kill();
                    }
                }
                _ => {}
            }
        });
}
