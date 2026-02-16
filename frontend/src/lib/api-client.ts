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

// ---------------------------------------------------------------------------
// Shared types (mirroring backend Pydantic schemas)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  database: string;
}

export type IncomeType = "SALARY" | "BONUS" | "OTHER";

export interface UserCreate {
  display_name?: string | null;
}

export interface UserResponse {
  id: string;
  display_name: string | null;
  created_at: string;
}

export interface IncomeEntryCreate {
  user_id: string;
  payment_date: string; // YYYY-MM-DD
  income_type: IncomeType;
  gross_amount: number;
  social_insurance?: number;
  withholding_tax?: number;
  resident_tax?: number;
}

export interface IncomeEntryResponse {
  id: number;
  user_id: string;
  payment_date: string | null;
  income_type: IncomeType;
  gross_amount: number;
  social_insurance: number;
  withholding_tax: number;
  resident_tax: number;
  source_file: string | null;
  raw_content: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Transport helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  return clientRequest<HealthResponse>("/health");
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export async function createUser(
  data: UserCreate,
): Promise<UserResponse> {
  return clientRequest<UserResponse>("/users", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getUser(userId: string): Promise<UserResponse> {
  return clientRequest<UserResponse>(`/users/${userId}`);
}

// ---------------------------------------------------------------------------
// Income Entries
// ---------------------------------------------------------------------------

export async function createIncomeEntry(
  data: IncomeEntryCreate,
): Promise<IncomeEntryResponse> {
  return clientRequest<IncomeEntryResponse>("/income-entries", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listIncomeEntries(
  userId: string,
): Promise<IncomeEntryResponse[]> {
  return clientRequest<IncomeEntryResponse[]>(`/income-entries/${userId}`);
}

export async function getIncomeEntry(
  userId: string,
  entryId: number,
): Promise<IncomeEntryResponse> {
  return clientRequest<IncomeEntryResponse>(
    `/income-entries/${userId}/${entryId}`,
  );
}

export async function deleteIncomeEntry(
  userId: string,
  entryId: number,
): Promise<void> {
  const res = await fetch(`/api/income-entries/${userId}/${entryId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
}
