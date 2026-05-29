let apiBaseUrl = "";
let desktopBackendInfo = null;
const BACKEND_READY_TIMEOUT_MS = 60_000;

export function isTauriRuntime() {
  return Boolean(window.__TAURI_INTERNALS__);
}

export function setApiBaseUrl(url) {
  apiBaseUrl = String(url || "").replace(/\/$/, "");
}

export function resolveApiUrl(url) {
  if (!apiBaseUrl || !url.startsWith("/api")) {
    return url;
  }
  return `${apiBaseUrl}${url}`;
}

export async function initDesktopBackend({ timeoutMs = BACKEND_READY_TIMEOUT_MS, onStatus = null } = {}) {
  if (!isTauriRuntime()) {
    return null;
  }

  const startedAt = Date.now();
  let lastStatus = null;
  while (Date.now() - startedAt < timeoutMs) {
    const status = await getDesktopBackendStatus();
    lastStatus = status;
    if (typeof onStatus === "function") {
      onStatus(status);
    }
    if (status?.ready && status.url) {
      desktopBackendInfo = backendInfoFromStatus(status);
      setApiBaseUrl(desktopBackendInfo.url);
      return desktopBackendInfo;
    }
    if (status?.error && !status.running && !status.starting) {
      throw new Error(status.error);
    }
    await sleep(status?.starting ? 300 : 600);
  }

  throw new Error(lastStatus?.error || "桌面后端启动超时，请打开日志查看详细信息");
}

export async function getDesktopBackendStatus() {
  if (!isTauriRuntime()) {
    return null;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("backend_status");
}

export async function getDesktopBackendLogs() {
  if (!isTauriRuntime()) {
    return {
      lines: ["Not running inside Tauri."],
      startup_error: "",
      backend: null,
    };
  }

  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("backend_logs");
}

export function getDesktopBackendInfo() {
  return desktopBackendInfo;
}

function backendInfoFromStatus(status) {
  return {
    url: status.url,
    health_url: status.health_url,
    port: status.port,
    pid: status.pid,
  };
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function pickDesktopFolder(title = "选择照片文件夹") {
  if (!isTauriRuntime()) {
    return null;
  }

  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    directory: true,
    multiple: false,
    title,
  });

  if (Array.isArray(selected)) {
    return selected[0] || null;
  }

  return typeof selected === "string" ? selected : null;
}

export async function openDesktopPath(path) {
  const target = String(path || "").trim();
  if (!target || !isTauriRuntime()) {
    return false;
  }

  const { openPath } = await import("@tauri-apps/plugin-opener");
  await openPath(target);
  return true;
}
