import { idToken } from "./auth";

export const API = ((import.meta.env.VITE_API_BASE as string | undefined) || "https://d3t20pvqqs9z05.cloudfront.net").replace(/\/$/, "");

export class AuthError extends Error {}

export type Level = "safe" | "warning" | "emergency" | "no_answer" | "calling" | "pending" | "declined" | "paused" | "none";
export type Hazard = "heat" | "cold";

export interface Weather {
  high_f?: number | null; low_f?: number | null; now_f?: number | null; now_label?: string; short?: string;
  alert?: { event: string; hazard: Hazard; headline?: string; ends?: string } | null;
}

export interface Person {
  id: string; name: string; first_name: string; relationship?: string | null; city?: string; state?: string;
  address?: string; language: string; hazards: Hazard[]; status: string; paused: boolean; level: Level;
  headline: string; facts: Record<string, string | string[]>; hazard_now?: Hazard | null;
  last_call_at?: string | null; next_call_at?: string | null; weather: Weather;
}

export interface PersonDetail extends Person {
  risk_factors: string[];
  contacts: { name: string; role: string; is_you: boolean; order: number }[];
  timeline: { at: string; text: string; kind: string }[];
  history: { id: string; at: string; purpose: string; hazard: Hazard; status: string; level?: string; summary?: string }[];
}

export interface Me { user: { _id: string; email: string; name: string; phone: string }; people: Person[] }

export interface Draft {
  name: string; relationship: string; phone: string; address: string; language: string; risk_notes: string[];
  backup_name: string; backup_phone: string; backup_relationship: string; backup_skipped: boolean; your_phone: string;
}

export const emptyDraft: Draft = {
  name: "", relationship: "", phone: "", address: "", language: "", risk_notes: [],
  backup_name: "", backup_phone: "", backup_relationship: "", backup_skipped: false, your_phone: "",
};

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await idToken();
  if (!token) throw new AuthError("signed out");
  const r = await fetch(API + path, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(init.headers || {}) },
  });
  if (r.status === 401) throw new AuthError("signed out");
  const body = r.status === 204 ? null : await r.json().catch(() => null);
  if (!r.ok) {
    const d = body?.detail;
    throw new Error(typeof d === "string" ? d : d?.error || "Something went wrong. Please try again.");
  }
  return body as T;
}

const post = <T>(path: string, data: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(data) });

export const api = {
  me: () => call<Me>("/family/me"),
  person: (id: string) => call<PersonDetail>(`/family/people/${id}`),
  assistant: (messages: { role: string; text: string }[], draft: Draft) =>
    post<{ reply: string; draft: Draft; ready: boolean; missing: string[] }>("/family/assistant", { messages, draft }),
  add: (draft: Draft) => post<{ person: Person; consent_call: Record<string, unknown> }>("/family/people", draft),
  retryConsent: (id: string) => post(`/family/people/${id}/consent-call`, {}),
  pause: (id: string, paused: boolean) => post(`/family/people/${id}/pause`, { paused }),
  checkNow: (id: string, hazard: Hazard) => post<Record<string, unknown>>(`/family/people/${id}/check-now`, { hazard }),
  remove: (id: string) => call(`/family/people/${id}`, { method: "DELETE" }),
  updateMe: (data: { name?: string; phone?: string }) => call("/family/me", { method: "PATCH", body: JSON.stringify(data) }),
};
