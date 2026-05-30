use std::{
    collections::VecDeque,
    env,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
};
use tauri::{AppHandle, Manager};

use crate::auth_config::{resolve_auth_server_url, AUTH_SERVER_URL_ENV};
use crate::paths::{
    bundled_sidecar_path, merged_backend_origins, resolve_app_root, resolve_python,
    should_use_bundled_sidecar,
};

use super::health::{backend_url_from_health_url, wait_for_health, wait_for_ready_line};
use super::logs::{append_backend_log, pipe_backend_output};
use super::{BackendInfo, BackendProcess, ReadyPayload};

fn start_backend(
    app_handle: &AppHandle,
    logs: Arc<Mutex<VecDeque<String>>>,
) -> Result<BackendProcess, String> {
    if should_use_bundled_sidecar(app_handle) {
        return start_bundled_sidecar(app_handle, logs);
    }

    let app_root = resolve_app_root()?;
    let python = resolve_python(&app_root);
    let auth_server_url = resolve_auth_server_url(app_handle)?;
    let mut command = Command::new(&python);
    command
        .current_dir(&app_root)
        .arg("app.py")
        .args(["--host", "127.0.0.1", "--port", "0", "--no-browser", "--json-ready"]);
    apply_sidecar_env(&mut command, auth_server_url.as_deref());
    let child = command
        .spawn()
        .map_err(|err| {
            format!(
                "无法启动 Python 后端：{}；python={}，app_root={}",
                err,
                python.display(),
                app_root.display()
            )
        })?;

    finish_backend_start(child, logs)
}


pub(crate) fn start_backend_async(
    app_handle: AppHandle,
    process: Arc<Mutex<Option<BackendProcess>>>,
    startup_error: Arc<Mutex<Option<String>>>,
    starting: Arc<Mutex<bool>>,
    logs: Arc<Mutex<VecDeque<String>>>,
) {
    if let Ok(mut guard) = starting.lock() {
        *guard = true;
    }
    if let Ok(mut guard) = startup_error.lock() {
        *guard = None;
    }
    append_backend_log(&logs, "[tauri] starting backend".to_string());

    thread::spawn(move || {
        match start_backend(&app_handle, Arc::clone(&logs)) {
            Ok(backend) => {
                append_backend_log(
                    &logs,
                    format!(
                        "[tauri] backend ready pid={} url={}",
                        backend.info.pid, backend.info.url
                    ),
                );
                if let Ok(mut guard) = process.lock() {
                    *guard = Some(backend);
                }
            }
            Err(err) => {
                eprintln!("[inkmoment-sidecar] startup failed: {err}");
                append_backend_log(&logs, format!("[tauri] startup failed: {err}"));
                if let Ok(mut guard) = startup_error.lock() {
                    *guard = Some(err);
                }
            }
        }
        if let Ok(mut guard) = starting.lock() {
            *guard = false;
        }
    });
}


fn start_bundled_sidecar(
    app_handle: &AppHandle,
    logs: Arc<Mutex<VecDeque<String>>>,
) -> Result<BackendProcess, String> {
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .map_err(|err| format!("无法解析 Tauri 资源目录：{err}"))?;
    let sidecar = bundled_sidecar_path(&resource_dir)
        .ok_or_else(|| format!("找不到打包后的 Python sidecar：{}", resource_dir.display()))?;

    let auth_server_url = resolve_auth_server_url(app_handle)?;
    let mut command = Command::new(&sidecar);
    command.args(["--host", "127.0.0.1", "--port", "0", "--no-browser", "--json-ready"]);
    apply_sidecar_env(&mut command, auth_server_url.as_deref());
    let child = command
        .spawn()
        .map_err(|err| format!("无法启动打包后的 Python sidecar：{}；path={}", err, sidecar.display()))?;

    finish_backend_start(child, logs)
}


fn apply_sidecar_env(command: &mut Command, auth_server_url: Option<&str>) {
    command
        .env("INKMOMENT_DEV_ORIGINS", merged_backend_origins())
        .env("INKMOMENT_APP_VERSION", env!("CARGO_PKG_VERSION"))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(url) = auth_server_url {
        command.env(AUTH_SERVER_URL_ENV, url);
    }
}


fn finish_backend_start(
    mut child: Child,
    logs: Arc<Mutex<VecDeque<String>>>,
) -> Result<BackendProcess, String> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "无法读取后端 stdout".to_string())?;
    let stderr = child.stderr.take();
    let ready_rx = pipe_backend_output(stdout, stderr, logs);
    let ready_line = match wait_for_ready_line(&mut child, ready_rx) {
        Ok(line) => line,
        Err(err) => {
            terminate_child(&mut child);
            return Err(err);
        }
    };
    let ready: ReadyPayload = match serde_json::from_str(&ready_line) {
        Ok(payload) => payload,
        Err(err) => {
            terminate_child(&mut child);
            return Err(format!("后端 ready 输出不是有效 JSON：{err}; line={ready_line}"));
        }
    };
    if ready.event != "ready" {
        terminate_child(&mut child);
        return Err(format!("后端 ready 事件异常：{}", ready.event));
    }
    if let Err(err) = wait_for_health(&ready.health_url) {
        terminate_child(&mut child);
        return Err(err);
    }
    let backend_url = match backend_url_from_health_url(&ready.health_url) {
        Ok(url) => url,
        Err(err) => {
            terminate_child(&mut child);
            return Err(err);
        }
    };

    Ok(BackendProcess {
        child,
        info: BackendInfo {
            url: backend_url,
            health_url: ready.health_url,
            port: ready.port,
            pid: ready.pid,
        },
    })
}


fn terminate_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}
