export async function fetchJSON(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const body = options.body && typeof options.body === "object"
    ? JSON.stringify(options.body)
    : options.body;

  if (body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, body, headers });
  const text = await response.text();
  let data = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.error || text || `HTTP ${response.status}`;
    throw new Error(message);
  }

  return data;
}

export function imageUrl(path, width) {
  const params = new URLSearchParams({ path });
  if (width) params.set("w", String(width));
  return `/api/image?${params.toString()}`;
}
