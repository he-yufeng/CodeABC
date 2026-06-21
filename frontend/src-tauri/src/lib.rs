use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;

// Holds the spawned backend sidecar so we can stop it when the app exits.
struct BackendProcess(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .manage(BackendProcess(Mutex::new(None)))
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // In a release build, start the bundled backend so the desktop app is
      // self-contained — the user doesn't have to run `python run.py`. In dev
      // the developer runs the backend themselves (uvicorn --reload), so skip.
      #[cfg(not(debug_assertions))]
      {
        use tauri_plugin_shell::ShellExt;
        match app.shell().sidecar("codeabc-backend") {
          Ok(command) => match command.spawn() {
            Ok((_rx, child)) => {
              app.state::<BackendProcess>().0.lock().unwrap().replace(child);
            }
            Err(e) => log::error!("failed to spawn backend sidecar: {e}"),
          },
          Err(e) => log::error!("failed to build backend sidecar command: {e}"),
        }
      }

      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application")
    .run(|app_handle, event| {
      // Stop the backend when the app exits so we don't leave an orphaned
      // server holding the port.
      if let tauri::RunEvent::ExitRequested { .. } = event {
        if let Some(child) = app_handle
          .state::<BackendProcess>()
          .0
          .lock()
          .unwrap()
          .take()
        {
          let _ = child.kill();
        }
      }
    });
}
