/**
 * Tiny typed API client for the FastAPI backend.
 *
 * Every request goes through `getJson`, giving us one place to add auth headers
 * (Phase 2), error handling, and base-URL configuration. Route-specific helpers
 * live on the `api` object so components never hard-code URLs.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PingResponse = { message: string };
export type HealthResponse = {
  status: string;
  service: string;
  environment: string;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Request to ${path} failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  baseUrl: API_URL,
  ping: () => getJson<PingResponse>("/api/ping"),
  health: () => getJson<HealthResponse>("/health"),
};
