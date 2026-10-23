// Tiny fetch wrapper: adds the JWT, refreshes it once on 401, and turns
// Django REST Framework error bodies into readable messages.
const KEY = "pharmatrack.auth";

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
}
let tokens = load();

export function setTokens(next) {
  tokens = next;
  try { next ? localStorage.setItem(KEY, JSON.stringify(next)) : localStorage.removeItem(KEY); } catch { /* storage blocked */ }
}
export const hasTokens = () => Boolean(tokens?.access);

let onLogout = () => {};
export const setLogoutHandler = (fn) => { onLogout = fn; };

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

function messageFrom(data, status) {
  if (!data) return `Request failed (${status}).`;
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  const parts = Object.entries(data).map(([field, value]) => {
    const text = Array.isArray(value) ? value.map((v) => (typeof v === "object" ? JSON.stringify(v) : v)).join(" ") : typeof value === "object" ? messageFrom(value) : value;
    return field === "non_field_errors" ? text : `${field.replaceAll("_", " ")}: ${text}`;
  });
  return parts.join(" ") || `Request failed (${status}).`;
}

async function refresh() {
  if (!tokens?.refresh) return false;
  const res = await fetch("/api/auth/refresh/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh: tokens.refresh }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  setTokens({ ...tokens, access: data.access });
  return true;
}

export async function api(path, { method = "GET", body, params, retry = true } = {}) {
  let url = path.startsWith("/api") ? path : `/api${path}`;
  if (params) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null && v !== false));
    if ([...qs].length) url += (url.includes("?") ? "&" : "?") + qs;
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (tokens?.access) headers.Authorization = `Bearer ${tokens.access}`;

  const res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (res.status === 401 && retry && tokens?.refresh) {
    if (await refresh()) return api(path, { method, body, params, retry: false });
    setTokens(null);
    onLogout();
  }
  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new ApiError(messageFrom(data, res.status), res.status, data);
  return data;
}

export const get = (path, params) => api(path, { params });
export const post = (path, body) => api(path, { method: "POST", body });
export const patch = (path, body) => api(path, { method: "PATCH", body });
export const put = (path, body) => api(path, { method: "PUT", body });
export const del = (path) => api(path, { method: "DELETE" });

// Fetch every page of a paginated list (fine for small catalogues like suppliers).
export async function getAll(path, params = {}) {
  let page = 1, out = [];
  for (;;) {
    const data = await get(path, { ...params, page });
    if (Array.isArray(data)) return data;
    out = out.concat(data.results);
    if (!data.next) return out;
    page += 1;
  }
}
