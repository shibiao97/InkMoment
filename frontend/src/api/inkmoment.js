import { fetchJSON } from "./http";

export function getBranding() {
  return fetchJSON("/api/branding");
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

export function getJob(since = 0) {
  return fetchJSON(`/api/job?since=${encodeURIComponent(String(since))}`);
}

export function cancelJob() {
  return fetchJSON("/api/cancel_job", {
    method: "POST",
  });
}

export function getStatus() {
  return fetchJSON("/api/status");
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
