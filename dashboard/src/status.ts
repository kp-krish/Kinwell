import type { Checkin, Resident } from "./api";

export type Status = "emergency" | "warning" | "no_answer" | "calling" | "safe" | "pending";

export const STATUS_META: Record<Status, { label: string; color: string; chip: string }> = {
  emergency: { label: "Emergency", color: "#dc2626", chip: "bg-red-100 text-red-800 ring-red-200" },
  warning: { label: "Needs attention", color: "#f59e0b", chip: "bg-amber-100 text-amber-800 ring-amber-200" },
  no_answer: { label: "No answer", color: "#6b7280", chip: "bg-stone-200 text-stone-700 ring-stone-300" },
  calling: { label: "On a call", color: "#2563eb", chip: "bg-blue-100 text-blue-800 ring-blue-200" },
  safe: { label: "Safe", color: "#16a34a", chip: "bg-green-100 text-green-800 ring-green-200" },
  pending: { label: "Not called yet", color: "#a8a29e", chip: "bg-stone-100 text-stone-600 ring-stone-200" },
};

export function latestByResident(checkins: Checkin[]): Map<string, Checkin> {
  const m = new Map<string, Checkin>();
  for (const c of checkins) {
    const prev = m.get(c.resident_id);
    if (!prev || new Date(c.started_at) > new Date(prev.started_at)) m.set(c.resident_id, c);
  }
  return m;
}

export function statusOf(_r: Resident, latest?: Checkin): Status {
  if (!latest) return "pending";
  if (["dialing", "in_progress"].includes(latest.call_status)) return "calling";
  if (latest.flags?.some((f) => f.level === "emergency") || latest.risk_level === "emergency") return "emergency";
  if (latest.call_status === "no_answer" || latest.risk_level === "no_answer") return "no_answer";
  if (latest.risk_level === "warning") return "warning";
  if (latest.call_status === "completed") return "safe";
  return "pending";
}
