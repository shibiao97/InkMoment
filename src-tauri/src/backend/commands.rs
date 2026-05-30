use tauri::State;

use super::{logs::append_backend_log, BackendInfo, BackendLogs, BackendState, BackendStatus};

#[tauri::command]
pub(crate) fn backend_info(state: State<'_, BackendState>) -> Result<BackendInfo, String> {
    let process = state
        .process
        .lock()
        .map_err(|_| "后端状态锁已损坏".to_string())?;
    if let Some(backend) = process.as_ref() {
        return Ok(backend.info.clone());
    }

    let error = state
        .startup_error
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(|| {
            if state.starting.lock().map(|guard| *guard).unwrap_or(false) {
                "后端正在启动".to_string()
            } else {
                "后端尚未启动".to_string()
            }
        });
    Err(error)
}

#[tauri::command]
pub(crate) fn backend_status(state: State<'_, BackendState>) -> Result<BackendStatus, String> {
    let mut process = state
        .process
        .lock()
        .map_err(|_| "后端状态锁已损坏".to_string())?;

    if let Some(backend) = process.as_mut() {
        let info = backend.info.clone();
        match backend
            .child
            .try_wait()
            .map_err(|err| format!("检查后端进程状态失败：{err}"))?
        {
            Some(status) => {
                let message = format!("后端进程已退出：{status}");
                append_backend_log(&state.logs, format!("[tauri] {message}"));
                *state
                    .startup_error
                    .lock()
                    .map_err(|_| "后端错误状态锁已损坏".to_string())? = Some(message.clone());
                *process = None;
                return Ok(BackendStatus {
                    ready: false,
                    running: false,
                    starting: false,
                    url: Some(info.url),
                    health_url: Some(info.health_url),
                    port: Some(info.port),
                    pid: Some(info.pid),
                    error: Some(message),
                    exit_status: Some(status.to_string()),
                });
            }
            None => {
                return Ok(BackendStatus {
                    ready: true,
                    running: true,
                    starting: false,
                    url: Some(info.url),
                    health_url: Some(info.health_url),
                    port: Some(info.port),
                    pid: Some(info.pid),
                    error: None,
                    exit_status: None,
                });
            }
        }
    }

    let starting = state.starting.lock().map(|guard| *guard).unwrap_or(false);
    if starting {
        return Ok(BackendStatus {
            ready: false,
            running: true,
            starting: true,
            url: None,
            health_url: None,
            port: None,
            pid: None,
            error: None,
            exit_status: None,
        });
    }

    let error = state
        .startup_error
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(|| "后端尚未启动".to_string());
    Ok(BackendStatus {
        ready: false,
        running: false,
        starting: false,
        url: None,
        health_url: None,
        port: None,
        pid: None,
        error: Some(error),
        exit_status: None,
    })
}

#[tauri::command]
pub(crate) fn backend_logs(state: State<'_, BackendState>) -> Result<BackendLogs, String> {
    let lines = state
        .logs
        .lock()
        .map_err(|_| "后端日志锁已损坏".to_string())?
        .iter()
        .cloned()
        .collect();
    let startup_error = state
        .startup_error
        .lock()
        .map_err(|_| "后端错误状态锁已损坏".to_string())?
        .clone();
    let backend = state
        .process
        .lock()
        .map_err(|_| "后端状态锁已损坏".to_string())?
        .as_ref()
        .map(|process| process.info.clone());
    Ok(BackendLogs {
        lines,
        startup_error,
        backend,
    })
}
