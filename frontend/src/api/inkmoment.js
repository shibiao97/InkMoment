import { fetchJSON } from "./http";
import { resolveApiUrl } from "./runtime";

export function getBranding() {
  return fetchJSON("/api/branding");
}

export function getHealth() {
  return fetchJSON("/api/health");
}

export function getAuthStatus(force = false) {
  const params = force ? "?force=1" : "";
  return fetchJSON(`/api/auth/status${params}`);
}

export function loginAuth(payload) {
  return fetchJSON("/api/auth/login", {
    method: "POST",
    body: payload,
  });
}

export function registerAuth(payload) {
  return fetchJSON("/api/auth/register", {
    method: "POST",
    body: payload,
  });
}

export function redeemAuthCdk(code) {
  return fetchJSON("/api/auth/redeem", {
    method: "POST",
    body: { code },
  });
}

export function unbindAuthDevice(payload) {
  return fetchJSON("/api/auth/device/unbind", {
    method: "POST",
    body: payload,
  });
}

export function logoutAuth() {
  return fetchJSON("/api/auth/logout", {
    method: "POST",
  });
}

export function peekFolder(folder) {
  return fetchJSON("/api/peek_folder", {
    method: "POST",
    body: { folder },
  });
}

export function startJob(payload) {
  return fetchJSON("/api/start", {
    method: "POST",
    body: payload,
  });
}

export function preflightDependencies(payload) {
  return fetchJSON("/api/dependencies/preflight", {
    method: "POST",
    body: payload,
  });
}

export function downloadDependencies(payload) {
  return fetchJSON("/api/dependencies/download", {
    method: "POST",
    body: payload,
  });
}

export function getDependencyDownloadStatus() {
  return fetchJSON("/api/dependencies/download/status");
}

export function getJob(since = 0) {
  return fetchJSON(`/api/job?since=${encodeURIComponent(String(since))}`);
}

export function streamJob(since = 0) {
  if (typeof window === "undefined" || typeof window.EventSource !== "function") {
    return null;
  }
  return new window.EventSource(resolveApiUrl(`/api/job/stream?since=${encodeURIComponent(String(since))}`));
}

export function getTaskHistory(limit = 20) {
  return fetchJSON(`/api/task_history?limit=${encodeURIComponent(String(limit))}`);
}

export function cancelJob() {
  return fetchJSON("/api/cancel_job", {
    method: "POST",
  });
}

export function getStatus() {
  return fetchJSON("/api/status");
}

export function resetSession() {
  return fetchJSON("/api/reset_session", {
    method: "POST",
  });
}

export function getAutoRejected() {
  return fetchJSON("/api/auto_rejected");
}

export function restoreRejected(payload) {
  return fetchJSON("/api/restore_rejected", {
    method: "POST",
    body: payload,
  });
}

export function confirmPrescreen() {
  return fetchJSON("/api/confirm_prescreen", {
    method: "POST",
  });
}

export function getGroupingProgress(since = 0) {
  return fetchJSON(`/api/grouping_progress?since=${encodeURIComponent(String(since))}`);
}

export function getPreviewGroups() {
  return fetchJSON("/api/preview_groups");
}

export function regroup(payload) {
  return fetchJSON("/api/regroup", {
    method: "POST",
    body: payload,
  });
}

export function getGroup() {
  return fetchJSON("/api/group");
}

export function chooseGroup(loser) {
  return fetchJSON("/api/choose", {
    method: "POST",
    body: { loser },
  });
}

export function skipGroup() {
  return fetchJSON("/api/skip_group", {
    method: "POST",
  });
}

export function undoGroup() {
  return fetchJSON("/api/undo", {
    method: "POST",
  });
}

export function reopenGroup(groupId) {
  return fetchJSON("/api/reopen_group", {
    method: "POST",
    body: { group_id: groupId },
  });
}

export function getWinners() {
  return fetchJSON("/api/winners");
}

export function getSkipped() {
  return fetchJSON("/api/skipped");
}

export function openFolder(payload = {}) {
  return fetchJSON("/api/open_folder", {
    method: "POST",
    body: payload,
  });
}

export function getWatermarkTemplates() {
  return fetchJSON("/api/watermark/templates");
}

export function previewWatermark(payload) {
  return fetchJSON("/api/watermark/preview", {
    method: "POST",
    body: payload,
  });
}

export function startWatermark(payload) {
  return fetchJSON("/api/watermark/start", {
    method: "POST",
    body: payload,
  });
}

export function getWatermarkStatus() {
  return fetchJSON("/api/watermark/status");
}

export function cancelWatermark() {
  return fetchJSON("/api/watermark/cancel", {
    method: "POST",
  });
}

export function openWatermarkOutputFolder() {
  return fetchJSON("/api/watermark/open_out_dir", {
    method: "POST",
  });
}

export function getArkKeyStatus() {
  return fetchJSON("/api/ark_key");
}

export function saveArkKey(payload) {
  return fetchJSON("/api/ark_key", {
    method: "POST",
    body: payload,
  });
}

export function clearArkKey() {
  return fetchJSON("/api/ark_key", {
    method: "DELETE",
  });
}

export function getLlmModels(force = false) {
  const params = force ? "?force=1" : "";
  return fetchJSON(`/api/llm_models${params}`);
}

export function getLlmConcurrency() {
  return fetchJSON("/api/llm_concurrency");
}

export function getDiagnostics() {
  return fetchJSON("/api/diagnostics");
}
