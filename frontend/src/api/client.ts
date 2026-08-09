import type { ApiErrorBody } from "../types/api";

// Relative — vite.config.ts proxies /api/* to the FastAPI backend in dev, so no CORS setup is needed on the backend (which stays "frozen at three endpoints" as scoped).
const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as ApiErrorBody;
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body — fall back to statusText already set above
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}
