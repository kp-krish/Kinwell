export const API = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "http://127.0.0.1:8080";

export type Point = { type: "Point"; coordinates: [number, number] };

export interface Resident {
  _id: string; name: string; first_name?: string; phone?: string; language?: string;
  address?: string; location: Point; zip?: string; risk_factors?: string[];
  playbook: "resident" | "crew"; crew_id?: string; crew_name?: string; employer?: string;
  enrolled_by?: string; demo?: boolean;
}
export interface Flag { level: "warning" | "emergency"; reason: string; at: string }
export interface CaseNote { summary: string; ac_status: string; symptoms: string[]; needs_human_today: boolean; reason: string; memory_summary: string; model?: string }
export interface Checkin {
  _id: string; resident_id: string; resident_name?: string; playbook?: string; started_at: string;
  ended_at?: string; call_status: string; risk_level?: string; risk_reasons?: string[];
  ac_working?: string; water?: string; rest_break?: string; symptoms?: string[]; flags?: Flag[];
  case_note?: CaseNote; memory_used?: string[]; attempt?: number; reason?: string; callback_at?: string;
  transcript?: { role: string; text: string }[]; demo?: boolean;
}
export interface Alert {
  _id: string; resident_id: string; resident_name?: string; playbook?: string; level: string; reason: string;
  notified: string[]; created_at: string; acknowledged_by?: string | null; resolved_at?: string | null;
}
export interface Resource {
  _id: string; type: string; name: string; address: string; location?: Point; hours_today?: string;
  open_today?: boolean; notes?: string; source_url?: string; fetched_at?: string;
}
export interface Crew { _id: string; name: string; employer: string; shift_start: string; shift_end: string; interval_min: number }
export interface ScoutRun {
  _id: string; source: string; url: string; started_at: string; finished_at?: string; status: string;
  sites_saved?: number; error?: string; log: { t: number; msg: string }[];
}
export interface State {
  residents: Resident[]; checkins: Checkin[]; alerts: Alert[]; resources: Resource[];
  crews: Crew[]; scout_runs: ScoutRun[]; server_time: string;
}
export interface Briefing { headline: string; calls: number; items: { resident_id: string; name: string; priority: number; reason: string }[]; model?: string }

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  state: () => j<State>("/api/state"),
  checkin: (id: string) => j<Checkin>(`/api/checkins/${id}`),
  briefing: () => j<Briefing>("/api/briefing"),
  ack: (id: string) => j(`/api/alerts/${id}/ack`, { method: "POST", body: JSON.stringify({ by: "caseworker" }) }),
  simulate: () => j<{ calls: unknown[]; scout: unknown }>("/api/simulate-heat-warning", { method: "POST", body: "{}" }),
  call: (person_id: string) => j("/calls", { method: "POST", body: JSON.stringify({ person_id, reason: "dashboard" }) }),
  refreshScout: () => j("/api/scout/refresh", { method: "POST", body: "{}" }),
};

export function ago(iso?: string, now = Date.now()): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

export function clock(iso?: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/Phoenix" });
}
