const API_BASE = "/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function getApiKey(): string | null {
  return localStorage.getItem("calseta_api_key");
}

export function setApiKey(key: string): void {
  localStorage.setItem("calseta_api_key", key);
}

export function clearApiKey(): void {
  localStorage.removeItem("calseta_api_key");
}

export function hasApiKey(): boolean {
  return !!getApiKey();
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const key = getApiKey();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (key) {
    headers["Authorization"] = `Bearer ${key}`;
  }
  if (
    options.body &&
    typeof options.body === "string" &&
    !headers["Content-Type"]
  ) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    // Stale or invalid API key — clear it so the login page shows
    if (res.status === 401 || res.status === 403) {
      clearApiKey();
      window.location.reload();
      throw new ApiError(res.status, "UNAUTHORIZED", "API key is invalid or expired");
    }

    let code = "UNKNOWN";
    let message = `HTTP ${res.status}`;
    let details: Record<string, unknown> = {};
    try {
      const body = await res.json();
      if (body.error) {
        code = body.error.code || code;
        message = body.error.message || message;
        details = body.error.details || details;
      }
    } catch {
      // ignore parse failures
    }
    throw new ApiError(res.status, code, message, details);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, {
      method: "POST",
      body: formData,
      // Don't set Content-Type — browser sets multipart boundary
    }),
};
