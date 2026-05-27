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
