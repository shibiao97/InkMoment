mod auth_config;
mod backend;
mod paths;

use std::{collections::VecDeque, sync::{Arc, Mutex}};
use tauri::Manager;

use backend::commands::{backend_info, backend_logs, backend_status};
use backend::{start_backend_async, BackendState};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let logs = Arc::new(Mutex::new(VecDeque::new()));
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(BackendState {
            process: Arc::new(Mutex::new(None)),
            startup_error: Arc::new(Mutex::new(None)),
            starting: Arc::new(Mutex::new(false)),
            logs,
        })
        .setup(|app| {
            let state = app.state::<BackendState>();
            start_backend_async(
                app.handle().clone(),
                Arc::clone(&state.process),
                Arc::clone(&state.startup_error),
                Arc::clone(&state.starting),
                Arc::clone(&state.logs),
            );
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend_info,
            backend_status,
            backend_logs
        ])
        .run(tauri::generate_context!())
        .expect("error while running InkMoment desktop shell");
}
