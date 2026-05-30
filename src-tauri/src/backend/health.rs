use std::{
    io::{Read, Write},
    net::{TcpStream, ToSocketAddrs},
    process::Child,
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

pub(crate) fn wait_for_ready_line(
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

pub(crate) fn wait_for_health(health_url: &str) -> Result<(), String> {
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

pub(crate) fn backend_url_from_health_url(health_url: &str) -> Result<String, String> {
    let (host, port, _) = parse_local_http_url(health_url)?;
    Ok(format!("http://{host}:{port}"))
}


#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

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

}
