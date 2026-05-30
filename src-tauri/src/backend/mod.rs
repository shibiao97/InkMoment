pub(crate) mod health;
pub(crate) mod commands;
mod launcher;
mod logs;

use serde::{Deserialize, Serialize};
use std::{
    collections::VecDeque,
    process::Child,
    sync::{Arc, Mutex},
};

pub(crate) use launcher::start_backend_async;

#[derive(Clone, Debug, Serialize)]
pub(crate) struct BackendInfo {
    pub(crate) url: String,
    pub(crate) health_url: String,
    pub(crate) port: u16,
    pub(crate) pid: u32,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct BackendStatus {
    pub(crate) ready: bool,
    pub(crate) running: bool,
    pub(crate) starting: bool,
    pub(crate) url: Option<String>,
    pub(crate) health_url: Option<String>,
    pub(crate) port: Option<u16>,
    pub(crate) pid: Option<u32>,
    pub(crate) error: Option<String>,
    pub(crate) exit_status: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct BackendLogs {
    pub(crate) lines: Vec<String>,
    pub(crate) startup_error: Option<String>,
    pub(crate) backend: Option<BackendInfo>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ReadyPayload {
    pub(crate) event: String,
    pub(crate) health_url: String,
    pub(crate) port: u16,
    pub(crate) pid: u32,
}

pub(crate) struct BackendProcess {
    pub(crate) child: Child,
    pub(crate) info: BackendInfo,
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub(crate) struct BackendState {
    pub(crate) process: Arc<Mutex<Option<BackendProcess>>>,
    pub(crate) startup_error: Arc<Mutex<Option<String>>>,
    pub(crate) starting: Arc<Mutex<bool>>,
    pub(crate) logs: Arc<Mutex<VecDeque<String>>>,
}
