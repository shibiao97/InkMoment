import { resolveApiUrl } from "./runtime";

export const AUTH_INVALID_EVENT = "inkmoment-auth-invalid";

const AUTH_INVALID_CODES = new Set([
  "auth_server_not_configured",
  "disabled",
  "device_mismatch",
  "expired",
  "revoked",
  "unauthenticated",
]);

export async function fetchJSON(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const body = options.body && typeof options.body === "object"
    ? JSON.stringify(options.body)
    : options.body;

  if (body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(resolveApiUrl(url), { ...options, body, headers });
  const text = await response.text();
  let data;

  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.error || text || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.code = data?.code || "";
    error.data = data;
    notifyAuthInvalid(url, response.status, data);
    throw error;
  }

  return data;
}

function notifyAuthInvalid(url, status, data) {
  const code = data?.code || data?.auth?.reason || "";
  if (!AUTH_INVALID_CODES.has(code)) return;
  if (status < 401) return;
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") return;
  const detail = {
    url,
    status,
    code,
    message: data?.error || "",
    auth: data?.auth || null,
  };
  window.dispatchEvent(new CustomEvent(AUTH_INVALID_EVENT, { detail }));
}

export function imageUrl(path, width) {
  const params = new URLSearchParams({ path });
  if (width) params.set("w", String(width));
  return resolveApiUrl(`/api/image?${params.toString()}`);
}
