let apiBaseUrl = "";
let desktopBackendInfo = null;

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

export async function initDesktopBackend() {
  if (!isTauriRuntime()) {
    return null;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  desktopBackendInfo = await invoke("backend_info");
  setApiBaseUrl(desktopBackendInfo.url);
  return desktopBackendInfo;
}

export async function getDesktopBackendStatus() {
  if (!isTauriRuntime()) {
    return null;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("backend_status");
}

export function getDesktopBackendInfo() {
  return desktopBackendInfo;
}
