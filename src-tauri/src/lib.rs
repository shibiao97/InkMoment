use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::{
    env,
    fs,
    io::{BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager, State};

const DEFAULT_BACKEND_ORIGINS: &str = concat!(
    "http://127.0.0.1:5173,",
    "http://localhost:5173,",
    "tauri://localhost,",
    "http://tauri.localhost,",
    "https://tauri.localhost"
);
const AUTH_SERVER_URL_ENV: &str = "INKMOMENT_AUTH_SERVER_URL";
const AUTH_CONFIG_PATH_ENV: &str = "INKMOMENT_AUTH_CONFIG";
const AUTH_CONFIG_RESOURCE_NAMES: &[&str] = &[
    "inkmoment-auth.json",
    "auth-config.json",
    "config/inkmoment-auth.json",
];
const MAX_BACKEND_LOG_LINES: usize = 500;

#[derive(Clone, Debug, Serialize)]
struct BackendInfo {
    url: String,
    health_url: String,
    port: u16,
    pid: u32,
}

#[derive(Clone, Debug, Serialize)]
struct BackendStatus {
    ready: bool,
    running: bool,
    starting: bool,
    url: Option<String>,
    health_url: Option<String>,
    port: Option<u16>,
    pid: Option<u32>,
    error: Option<String>,
    exit_status: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
struct BackendLogs {
    lines: Vec<String>,
    startup_error: Option<String>,
    backend: Option<BackendInfo>,
}

#[derive(Debug, Deserialize)]
struct ReadyPayload {
    event: String,
    health_url: String,
    port: u16,
    pid: u32,
}

#[derive(Debug, Deserialize)]
struct AuthConfigFile {
    auth_server_url: Option<String>,
    server_url: Option<String>,
    base_url: Option<String>,
}

struct BackendProcess {
    child: Child,
    info: BackendInfo,
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

struct BackendState {
    process: Arc<Mutex<Option<BackendProcess>>>,
    startup_error: Arc<Mutex<Option<String>>>,
    starting: Arc<Mutex<bool>>,
    logs: Arc<Mutex<VecDeque<String>>>,
}

#[tauri::command]
fn backend_info(state: State<'_, BackendState>) -> Result<BackendInfo, String> {
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
fn backend_status(state: State<'_, BackendState>) -> Result<BackendStatus, String> {
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
fn backend_logs(state: State<'_, BackendState>) -> Result<BackendLogs, String> {
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

fn start_backend_async(
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

fn resolve_auth_server_url(app_handle: &AppHandle) -> Result<Option<String>, String> {
    if let Some(url) = non_empty_env(AUTH_SERVER_URL_ENV) {
        return normalize_auth_server_url(&url, AUTH_SERVER_URL_ENV);
    }

    if let Some(path) = non_empty_env(AUTH_CONFIG_PATH_ENV) {
        return read_auth_config_file(&PathBuf::from(path));
    }

    let Some(resource_dir) = app_handle.path().resource_dir().ok() else {
        return Ok(None);
    };
    for resource_name in AUTH_CONFIG_RESOURCE_NAMES {
        let candidate = resource_dir.join(resource_name);
        if candidate.is_file() {
            return read_auth_config_file(&candidate);
        }
    }
    Ok(None)
}

fn read_auth_config_file(path: &Path) -> Result<Option<String>, String> {
    let content = fs::read_to_string(path)
        .map_err(|err| format!("读取授权配置失败：{}；path={}", err, path.display()))?;
    let config: AuthConfigFile = serde_json::from_str(&content)
        .map_err(|err| format!("授权配置不是有效 JSON：{}；path={}", err, path.display()))?;
    let url = config
        .auth_server_url
        .or(config.server_url)
        .or(config.base_url)
        .unwrap_or_default();
    normalize_auth_server_url(&url, &path.display().to_string())
}

fn normalize_auth_server_url(value: &str, source: &str) -> Result<Option<String>, String> {
    let url = value.trim().trim_end_matches('/').to_string();
    if url.is_empty() {
        return Ok(None);
    }
    if !url.starts_with("https://") && !url.starts_with("http://") {
        return Err(format!("{source} 必须是 http 或 https URL"));
    }
    Ok(Some(url))
}

fn non_empty_env(name: &str) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn bundled_sidecar_path(resource_dir: &Path) -> Option<PathBuf> {
    let mut base_names = vec!["inkmoment-sidecar".to_string()];
    if let Some(target) = option_env!("TARGET") {
        base_names.push(format!("inkmoment-sidecar-{target}"));
    }
    for dir in bundled_sidecar_search_dirs(resource_dir) {
        for base_name in &base_names {
            let mut candidate = dir.join(base_name);
            if cfg!(windows) {
                candidate.set_extension("exe");
            }
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

fn bundled_sidecar_search_dirs(resource_dir: &Path) -> Vec<PathBuf> {
    let mut dirs = vec![
        resource_dir.join("binaries").join("inkmoment-sidecar"),
        resource_dir.join("inkmoment-sidecar"),
        resource_dir.to_path_buf(),
    ];
    if cfg!(target_os = "macos")
        && resource_dir.file_name().and_then(|name| name.to_str()) == Some("Resources")
    {
        if let Some(contents_dir) = resource_dir.parent() {
            dirs.push(contents_dir.join("MacOS"));
        }
    }
    dirs
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

fn should_use_bundled_sidecar(app_handle: &AppHandle) -> bool {
    if matches!(env::var("INKMOMENT_USE_BUNDLED_SIDECAR"), Ok(value) if value == "0" || value.eq_ignore_ascii_case("false"))
    {
        return false;
    }
    if matches!(env::var("INKMOMENT_USE_BUNDLED_SIDECAR"), Ok(value) if value == "1" || value.eq_ignore_ascii_case("true"))
    {
        return true;
    }
    app_handle
        .path()
        .resource_dir()
        .ok()
        .and_then(|resource_dir| bundled_sidecar_path(&resource_dir))
        .is_some()
}

fn resolve_app_root() -> Result<PathBuf, String> {
    if let Ok(root) = env::var("INKMOMENT_APP_ROOT") {
        let root = PathBuf::from(root);
        if root.join("app.py").is_file() {
            return Ok(root);
        }
        return Err(format!("INKMOMENT_APP_ROOT 下找不到 app.py：{}", root.display()));
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法解析项目根目录".to_string())
}

fn resolve_python(app_root: &Path) -> PathBuf {
    if let Ok(python) = env::var("INKMOMENT_PYTHON") {
        if !python.trim().is_empty() {
            return PathBuf::from(python);
        }
    }

    let venv_python = if cfg!(windows) {
        app_root.join(".venv").join("Scripts").join("python.exe")
    } else {
        app_root.join(".venv").join("bin").join("python")
    };
    if venv_python.is_file() {
        return venv_python;
    }

    PathBuf::from("python3")
}

fn merged_backend_origins() -> String {
    match env::var("INKMOMENT_DEV_ORIGINS") {
        Ok(existing) if !existing.trim().is_empty() => {
            format!("{existing},{DEFAULT_BACKEND_ORIGINS}")
        }
        _ => DEFAULT_BACKEND_ORIGINS.to_string(),
    }
}

fn pipe_backend_output(
    stdout: impl Read + Send + 'static,
    stderr: Option<impl Read + Send + 'static>,
    logs: Arc<Mutex<VecDeque<String>>>,
) -> mpsc::Receiver<Result<String, String>> {
    let (tx, rx) = mpsc::channel();
    let stdout_logs = Arc::clone(&logs);
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        let mut sent_ready = false;
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    eprintln!("[inkmoment-sidecar] {line}");
                    append_backend_log(&stdout_logs, format!("[stdout] {line}"));
                    if !sent_ready {
                        let _ = tx.send(Ok(line));
                        sent_ready = true;
                    }
                }
                Err(err) => {
                    append_backend_log(&stdout_logs, format!("[stdout:error] {err}"));
                    if !sent_ready {
                        let _ = tx.send(Err(format!("读取后端 ready 输出失败：{err}")));
                    }
                    break;
                }
            }
        }
    });

    if let Some(stderr) = stderr {
        let stderr_logs = Arc::clone(&logs);
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                eprintln!("[inkmoment-sidecar:stderr] {line}");
                append_backend_log(&stderr_logs, format!("[stderr] {line}"));
            }
        });
    }

    rx
}

fn append_backend_log(logs: &Arc<Mutex<VecDeque<String>>>, line: String) {
    if let Ok(mut guard) = logs.lock() {
        if guard.len() >= MAX_BACKEND_LOG_LINES {
            guard.pop_front();
        }
        guard.push_back(line);
    }
}

fn wait_for_ready_line(
    child: &mut Child,
    rx: mpsc::Receiver<Result<String, String>>,
) -> Result<String, String> {
    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if let Some(status) = child
            .try_wait()
            .map_err(|err| format!("检查后端进程状态失败：{err}"))?
        {
            return Err(format!("后端启动前已退出：{status}"));
        }
        match rx.recv_timeout(Duration::from_millis(100)) {
            Ok(result) => return result,
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err("后端 stdout 已关闭，未收到 ready 输出".to_string());
            }
        }
    }
    Err("等待后端 ready 输出超时".to_string())
}

fn wait_for_health(health_url: &str) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(8);
    let mut last_error = "尚未发起健康检查".to_string();
    while Instant::now() < deadline {
        match check_health_once(health_url) {
            Ok(()) => return Ok(()),
            Err(err) => last_error = err,
        }
        thread::sleep(Duration::from_millis(200));
    }
    Err(format!("后端健康检查未通过：{last_error}"))
}

fn check_health_once(health_url: &str) -> Result<(), String> {
    let (host, port, path) = parse_local_http_url(health_url)?;
    let addr = (host.as_str(), port)
        .to_socket_addrs()
        .map_err(|err| format!("解析健康检查地址失败：{err}"))?
        .next()
        .ok_or_else(|| "健康检查地址为空".to_string())?;
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(500))
        .map_err(|err| format!("连接健康检查失败：{err}"))?;
    stream
        .set_read_timeout(Some(Duration::from_millis(1200)))
        .map_err(|err| format!("设置健康检查读超时失败：{err}"))?;
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|err| format!("发送健康检查请求失败：{err}"))?;

    let response = read_health_response(&mut stream)?;
    if health_response_is_ready(&response) {
        Ok(())
    } else {
        Err("健康检查响应不是 ready 状态".to_string())
    }
}

fn read_health_response(stream: &mut TcpStream) -> Result<Vec<u8>, String> {
    let mut response = Vec::new();
    let mut buffer = [0_u8; 512];
    let deadline = Instant::now() + Duration::from_millis(2500);
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(n) => {
                response.extend_from_slice(&buffer[..n]);
                if health_response_is_ready(&response) {
                    return Ok(response);
                }
                if response.len() > 8192 {
                    break;
                }
            }
            Err(err)
                if matches!(
                    err.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                if health_response_is_ready(&response) {
                    return Ok(response);
                }
                if Instant::now() >= deadline {
                    return Err(format!("读取健康检查响应超时：{err}"));
                }
                thread::sleep(Duration::from_millis(20));
            }
            Err(err) => return Err(format!("读取健康检查响应失败：{err}")),
        }
    }
    Ok(response)
}

fn health_response_is_ready(response: &[u8]) -> bool {
    let text = String::from_utf8_lossy(response);
    (text.starts_with("HTTP/1.1 200") || text.starts_with("HTTP/1.0 200"))
        && text.contains("\"ok\":true")
}

fn parse_local_http_url(url: &str) -> Result<(String, u16, String), String> {
    let rest = url
        .strip_prefix("http://")
        .ok_or_else(|| format!("只支持 http 健康检查地址：{url}"))?;
    let (host_port, path) = match rest.split_once('/') {
        Some((host_port, path)) => (host_port, format!("/{path}")),
        None => (rest, "/".to_string()),
    };
    let (host, port) = host_port
        .rsplit_once(':')
        .ok_or_else(|| format!("健康检查地址缺少端口：{url}"))?;
    let port = port
        .parse::<u16>()
        .map_err(|err| format!("健康检查端口无效：{err}"))?;
    Ok((host.to_string(), port, path))
}

fn backend_url_from_health_url(health_url: &str) -> Result<String, String> {
    let (host, port, _) = parse_local_http_url(health_url)?;
    Ok(format!("http://{host}:{port}"))
}

fn terminate_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn normalize_auth_server_url_trims_trailing_slashes() {
        assert_eq!(
            normalize_auth_server_url(" https://auth.example.com/// ", "test").unwrap(),
            Some("https://auth.example.com".to_string())
        );
    }

    #[test]
    fn normalize_auth_server_url_rejects_non_http_urls() {
        let err = normalize_auth_server_url("file:///tmp/auth.json", "test").unwrap_err();
        assert!(err.contains("必须是 http 或 https URL"));
    }

    #[test]
    fn read_auth_config_file_accepts_primary_and_compat_keys() {
        let primary = write_temp_auth_config(r#"{"auth_server_url":"https://auth.example.com/"}"#);
        assert_eq!(
            read_auth_config_file(&primary).unwrap(),
            Some("https://auth.example.com".to_string())
        );
        let _ = fs::remove_file(primary);

        let compat = write_temp_auth_config(r#"{"server_url":"http://127.0.0.1:8061/"}"#);
        assert_eq!(
            read_auth_config_file(&compat).unwrap(),
            Some("http://127.0.0.1:8061".to_string())
        );
        let _ = fs::remove_file(compat);
    }

    #[test]
    fn bundled_sidecar_search_dirs_include_macos_executable_dir() {
        let resource_dir = PathBuf::from("/tmp/InkMoment.app/Contents/Resources");
        let dirs = bundled_sidecar_search_dirs(&resource_dir);
        assert!(dirs.contains(&resource_dir));
        assert!(dirs.contains(
            &PathBuf::from("/tmp/InkMoment.app/Contents/Resources")
                .join("binaries")
                .join("inkmoment-sidecar")
        ));
        if cfg!(target_os = "macos") {
            assert!(dirs.contains(&PathBuf::from("/tmp/InkMoment.app/Contents/MacOS")));
        }
    }

    #[test]
    fn health_response_ready_accepts_partial_response_after_body_arrives() {
        assert!(health_response_is_ready(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"ok\":true"
        ));
    }

    #[test]
    fn health_response_ready_rejects_non_ok_response() {
        assert!(!health_response_is_ready(
            b"HTTP/1.1 503 Service Unavailable\r\n\r\n{\"ok\":false}"
        ));
    }

    #[test]
    fn check_health_accepts_delayed_body_after_headers() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 256];
            let _ = stream.read(&mut request);
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n")
                .unwrap();
            thread::sleep(Duration::from_millis(1100));
            stream.write_all(b"{\"ok\":true}").unwrap();
        });

        assert!(check_health_once(&format!("http://127.0.0.1:{port}/api/health")).is_ok());
    }

    #[test]
    fn append_backend_log_keeps_recent_lines() {
        let logs = Arc::new(Mutex::new(VecDeque::new()));
        for i in 0..(MAX_BACKEND_LOG_LINES + 3) {
            append_backend_log(&logs, format!("line-{i}"));
        }
        let guard = logs.lock().expect("logs lock");
        assert_eq!(guard.len(), MAX_BACKEND_LOG_LINES);
        assert_eq!(guard.front().map(String::as_str), Some("line-3"));
        let expected_last = format!("line-{}", MAX_BACKEND_LOG_LINES + 2);
        assert_eq!(guard.back().map(String::as_str), Some(expected_last.as_str()));
    }

    fn write_temp_auth_config(content: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock before unix epoch")
            .as_nanos();
        let path = env::temp_dir().join(format!("inkmoment-auth-test-{nanos}.json"));
        fs::write(&path, content).expect("write temp auth config");
        path
    }
}
