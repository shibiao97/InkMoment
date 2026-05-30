use std::{
    collections::VecDeque,
    io::{BufRead, BufReader, Read},
    sync::{mpsc, Arc, Mutex},
    thread,
};

const MAX_BACKEND_LOG_LINES: usize = 500;

pub(crate) fn pipe_backend_output(
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

pub(crate) fn append_backend_log(logs: &Arc<Mutex<VecDeque<String>>>, line: String) {
    if let Ok(mut guard) = logs.lock() {
        if guard.len() >= MAX_BACKEND_LOG_LINES {
            guard.pop_front();
        }
        guard.push_back(line);
    }
}


#[cfg(test)]
mod tests {
    use super::*;

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

}
