/**
 * API client for the TaxPilot FastAPI backend.
 *
 * Server-side code (RSC, Route Handlers) uses API_SERVER_BASE which resolves
 * to the Docker-internal hostname (http://api:8000).
 *
 * Client-side code uses relative URLs (/api/...) that hit Next.js Route
 * Handlers, which proxy requests to the backend. This avoids CORS issues
 * and Docker hostname resolution problems in the browser.
 */

/** Base URL for server-side requests (resolved inside Docker network). */
const API_SERVER_BASE =
  process.env.API_SERVER_BASE ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  database: string;
}

/**
 * Server-side fetch to the FastAPI backend.
 * Only call this from RSC or Route Handlers — never from "use client" code.
 */
export async function serverRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_SERVER_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}

/**
 * Client-side fetch through the Next.js proxy (/api/...).
 * Safe to call from "use client" components.
 */
export async function clientRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}

/** Client-side health check via the Next.js proxy. */
export async function getHealth(): Promise<HealthResponse> {
  return clientRequest<HealthResponse>("/health");
}
