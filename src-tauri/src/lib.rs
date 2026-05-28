use serde::{Deserialize, Serialize};
use std::{
    env,
    io::{BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{mpsc, Mutex},
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
    url: Option<String>,
    health_url: Option<String>,
    port: Option<u16>,
    pid: Option<u32>,
    error: Option<String>,
    exit_status: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ReadyPayload {
    event: String,
    health_url: String,
    port: u16,
    pid: u32,
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
    process: Mutex<Option<BackendProcess>>,
    startup_error: Mutex<Option<String>>,
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
        .unwrap_or_else(|| "后端尚未启动".to_string());
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
                *state
                    .startup_error
                    .lock()
                    .map_err(|_| "后端错误状态锁已损坏".to_string())? = Some(message.clone());
                *process = None;
                return Ok(BackendStatus {
                    ready: false,
                    running: false,
                    url: Some(info.url),
                    health_url: Some(info.health_url),
                    port: Some(info.port),
                    pid: Some(info.pid),
                    error: Some(message),
                    exit_status: Some(status.to_string()),
                });
            }
            None => {
                let health_error = check_health_once(&info.health_url).err();
                return Ok(BackendStatus {
                    ready: health_error.is_none(),
                    running: true,
                    url: Some(info.url),
                    health_url: Some(info.health_url),
                    port: Some(info.port),
                    pid: Some(info.pid),
                    error: health_error,
                    exit_status: None,
                });
            }
        }
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
        url: None,
        health_url: None,
        port: None,
        pid: None,
        error: Some(error),
        exit_status: None,
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(BackendState {
            process: Mutex::new(None),
            startup_error: Mutex::new(None),
        })
        .setup(|app| {
            let state = app.state::<BackendState>();
            match start_backend(app.handle()) {
                Ok(backend) => {
                    *state.process.lock().expect("backend state lock") = Some(backend);
                }
                Err(err) => {
                    eprintln!("[inkmoment-sidecar] startup failed: {err}");
                    *state.startup_error.lock().expect("backend error lock") = Some(err);
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_info, backend_status])
        .run(tauri::generate_context!())
        .expect("error while running InkMoment desktop shell");
}

fn start_backend(app_handle: &AppHandle) -> Result<BackendProcess, String> {
    if should_use_bundled_sidecar(app_handle) {
        return start_bundled_sidecar(app_handle);
    }

    let app_root = resolve_app_root()?;
    let python = resolve_python(&app_root);
    let child = Command::new(&python)
        .current_dir(&app_root)
        .arg("app.py")
        .args(["--host", "127.0.0.1", "--port", "0", "--no-browser", "--json-ready"])
        .env("INKMOMENT_DEV_ORIGINS", merged_backend_origins())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| {
            format!(
                "无法启动 Python 后端：{}；python={}，app_root={}",
                err,
                python.display(),
                app_root.display()
            )
        })?;

    finish_backend_start(child)
}

fn start_bundled_sidecar(app_handle: &AppHandle) -> Result<BackendProcess, String> {
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .map_err(|err| format!("无法解析 Tauri 资源目录：{err}"))?;
    let sidecar = bundled_sidecar_path(&resource_dir)
        .ok_or_else(|| format!("找不到打包后的 Python sidecar：{}", resource_dir.display()))?;

    let child = Command::new(&sidecar)
        .args(["--host", "127.0.0.1", "--port", "0", "--no-browser", "--json-ready"])
        .env("INKMOMENT_DEV_ORIGINS", merged_backend_origins())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("无法启动打包后的 Python sidecar：{}；path={}", err, sidecar.display()))?;

    finish_backend_start(child)
}

fn bundled_sidecar_path(resource_dir: &Path) -> Option<PathBuf> {
    let mut base_names = vec!["inkmoment-sidecar".to_string()];
    if let Some(target) = option_env!("TARGET") {
        base_names.push(format!("inkmoment-sidecar-{target}"));
    }
    for base_name in base_names {
        let mut candidate = resource_dir.join(base_name);
        if cfg!(windows) {
            candidate.set_extension("exe");
        }
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn finish_backend_start(mut child: Child) -> Result<BackendProcess, String> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "无法读取后端 stdout".to_string())?;
    let stderr = child.stderr.take();
    let ready_rx = pipe_backend_output(stdout, stderr);
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
) -> mpsc::Receiver<Result<String, String>> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        let mut sent_ready = false;
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    eprintln!("[inkmoment-sidecar] {line}");
                    if !sent_ready {
                        let _ = tx.send(Ok(line));
                        sent_ready = true;
                    }
                }
                Err(err) => {
                    if !sent_ready {
                        let _ = tx.send(Err(format!("读取后端 ready 输出失败：{err}")));
                    }
                    break;
                }
            }
        }
    });

    if let Some(stderr) = stderr {
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                eprintln!("[inkmoment-sidecar:stderr] {line}");
            }
        });
    }

    rx
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
        .set_read_timeout(Some(Duration::from_millis(700)))
        .map_err(|err| format!("设置健康检查读超时失败：{err}"))?;
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|err| format!("发送健康检查请求失败：{err}"))?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|err| format!("读取健康检查响应失败：{err}"))?;
    if (response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200"))
        && response.contains("\"ok\":true")
    {
        Ok(())
    } else {
        Err("健康检查响应不是 ready 状态".to_string())
    }
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
