import { resolveApiUrl } from "./runtime";

export const AUTH_INVALID_EVENT = "inkmoment-auth-invalid";
const REQUEST_TIMEOUT_CODE = "request_timeout";

const AUTH_INVALID_CODES = new Set([
  "auth_server_not_configured",
  "disabled",
  "device_mismatch",
  "expired",
  "revoked",
  "unauthenticated",
]);

export async function fetchJSON(url, options = {}) {
  const { timeoutMs = 0, signal, ...fetchOptions } = options;
  const headers = { ...(options.headers || {}) };
  const body = fetchOptions.body && typeof fetchOptions.body === "object"
    ? JSON.stringify(fetchOptions.body)
    : fetchOptions.body;

  if (body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const timeoutController = createTimeoutController(timeoutMs, signal);
  let response;
  let text;
  try {
    response = await fetch(resolveApiUrl(url), {
      ...fetchOptions,
      body,
      headers,
      signal: timeoutController.signal,
    });
    text = await response.text();
  } catch (err) {
    if (timeoutController.timedOut) {
      const error = new Error("请求超时");
      error.status = 0;
      error.code = REQUEST_TIMEOUT_CODE;
      throw error;
    }
    throw err;
  } finally {
    timeoutController.clear();
  }
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

function createTimeoutController(timeoutMs, upstreamSignal) {
  let timedOut = false;
  let timeoutId = null;
  if (!Number.isFinite(Number(timeoutMs)) || Number(timeoutMs) <= 0 || typeof AbortController !== "function") {
    return {
      get timedOut() {
        return false;
      },
      signal: upstreamSignal,
      clear() {},
    };
  }
  const controller = new AbortController();
  const timeout = Number(timeoutMs);
  const abortFromUpstream = () => controller.abort(upstreamSignal?.reason);
  if (upstreamSignal?.aborted) {
    abortFromUpstream();
  } else if (upstreamSignal?.addEventListener) {
    upstreamSignal.addEventListener("abort", abortFromUpstream, { once: true });
  }
  timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeout);
  return {
    get timedOut() {
      return timedOut;
    },
    signal: controller.signal,
    clear() {
      if (timeoutId) clearTimeout(timeoutId);
      if (upstreamSignal?.removeEventListener) {
        upstreamSignal.removeEventListener("abort", abortFromUpstream);
      }
    },
  };
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
