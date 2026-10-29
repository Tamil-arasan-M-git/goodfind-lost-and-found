const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();

// Keep local development convenient while allowing deployed clients to choose their API origin.
export const API_BASE = (configuredBase || "http://127.0.0.1:8000").replace(/\/$/, "");

export function apiUrl(path) {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
