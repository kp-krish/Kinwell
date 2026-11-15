import type { Checkin, Resident } from "./api";

export type Status = "emergency" | "warning" | "no_answer" | "calling" | "safe" | "pending";

export const STATUS_META: Record<Status, { label: string; color: string; chip: string }> = {
  emergency: { label: "Emergency", color: "#FF8F80", chip: "bg-[#FF8F80] text-[#2A0D09]" },
  warning: { label: "Needs attention", color: "#F2C46B", chip: "bg-[#F2C46B] text-[#2B1C02]" },
  no_answer: { label: "No answer", color: "#B9B1C8", chip: "bg-white/15 text-white" },
  calling: { label: "On a call", color: "#8DB4E8", chip: "bg-[#8DB4E8]/25 text-[#CFE0F7]" },
  safe: { label: "Safe", color: "#8FD3A8", chip: "bg-[#8FD3A8]/20 text-[#B7E4C6]" },
  pending: { label: "Not called yet", color: "#7D7590", chip: "bg-white/10 text-[#C9C1D6]" },
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
