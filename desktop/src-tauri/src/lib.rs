use std::io::BufReader;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

struct ServerProcess(Mutex<Option<Child>>);

fn find_repo_root() -> Option<std::path::PathBuf> {
    let mut p = std::env::current_dir().ok()?;
    loop {
        if p.join("cli.py").exists() {
            return Some(p);
        }
        p = p.parent()?;
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Spawn the Python server from the repo root (where cli.py lives)
            let repo = find_repo_root().expect("cli.py not found in any parent directory");
            let child = Command::new("python3")
                .args(["cli.py", "--serve", "8765"])
                .current_dir(&repo)
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .expect("Failed to start python3; is it installed and on PATH?");

            // Drain stdout so the pipe doesn't fill up
            let out = child.stdout.expect("no stdout");
            std::thread::spawn(move || {
                for _line in BufReader::new(out).lines() {
                    // discard — keeps the pipe drained
                }
            });

            app.manage(ServerProcess(Mutex::new(Some(child))));

            // Kill the Python server when the window closes
            app.on_window_event(move |_window, event| {
                if let tauri::WindowEvent::CloseRequested { .. } = event {
                    if let Some(state) = handle.try_state::<ServerProcess>() {
                        if let Ok(mut guard) = state.0.lock() {
                            if let Some(ref mut child) = *guard {
                                let _ = child.kill();
                                let _ = child.wait();
                            }
                        }
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
