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
