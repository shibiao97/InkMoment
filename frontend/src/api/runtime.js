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

export async function pickDesktopFolder() {
  if (!isTauriRuntime()) {
    return null;
  }

  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    directory: true,
    multiple: false,
    title: "选择照片文件夹",
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
