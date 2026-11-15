import type { Hazard, Level, Person } from "./api";

export function Logo({ size = 26 }: { size?: number }) {
  return <span className="serif italic" style={{ fontSize: size }}>Kinwell</span>;
}

export const LEVEL: Record<Level, { label: string; orb: string; pill: string }> = {
  safe: { label: "Safe", orb: "orb-safe", pill: "bg-[rgba(63,107,87,0.13)] text-[#33594A]" },
  warning: { label: "Warning", orb: "orb-warn", pill: "bg-[rgba(180,83,42,0.12)] text-[#9A4321]" },
  emergency: { label: "Emergency", orb: "orb-emergency", pill: "bg-[#B42318] text-white" },
  no_answer: { label: "No answer", orb: "orb-warn", pill: "bg-[rgba(180,83,42,0.12)] text-[#9A4321]" },
  calling: { label: "Calling now", orb: "orb-calling", pill: "bg-[rgba(47,93,138,0.12)] text-[#2A5580]" },
  pending: { label: "Waiting for yes", orb: "orb-pending", pill: "bg-[rgba(38,33,46,0.07)] text-[#4A4356]" },
  declined: { label: "Said no", orb: "orb-quiet", pill: "bg-[rgba(38,33,46,0.07)] text-[#4A4356]" },
  paused: { label: "Paused", orb: "orb-quiet", pill: "bg-[rgba(38,33,46,0.07)] text-[#4A4356]" },
  none: { label: "All quiet", orb: "orb-quiet", pill: "bg-[rgba(38,33,46,0.07)] text-[#4A4356]" },
};

export function Pill({ level }: { level: Level }) {
  const l = LEVEL[level];
  return <span className={`shrink-0 rounded-full px-3 py-1.5 text-[13px] font-semibold ${l.pill}`}>{l.label}</span>;
}

export function Orb({ level, size = 46 }: { level: Level; size?: number }) {
  return <span aria-hidden="true" className={`orb ${LEVEL[level].orb}`} style={{ width: size, height: size }} />;
}

export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <span className="b1" /><span className="b2" /><span className="b3" />
    </div>
  );
}

export function time(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  const t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return today ? t : `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${t}`;
}

export function minutesUntil(iso?: string | null) {
  if (!iso) return null;
  return Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
}

export function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** Heat or cold mood: the most urgent active alert wins, else the season. */
export function autoMode(people: Person[]): Hazard {
  const hz = people.map((p) => p.weather?.alert?.hazard || p.hazard_now).find(Boolean);
  if (hz) return hz as Hazard;
  const m = new Date().getMonth();
  return m >= 10 || m <= 2 ? "cold" : "heat";
}

const FACT_LABELS: Record<string, string> = {
  ac_working: "AC", water: "Water", symptoms: "Feeling", heat_working: "Heater", indoor_temp: "Inside",
  indoor_heat: "Inside", power_on: "Power and gas", unsafe_heating: "Unsafe heat source",
};

export function factTiles(facts: Record<string, string | string[]>) {
  const out: { label: string; value: string; bad: boolean }[] = [];
  for (const [k, v] of Object.entries(facts)) {
    if (!FACT_LABELS[k]) continue;
    if (k === "symptoms") {
      const s = (v as string[]) || [];
      out.push({ label: "Feeling", value: s.length ? s.join(", ") : "No symptoms", bad: s.length > 0 });
      continue;
    }
    const val = String(v);
    if (val === "unknown") continue;
    if (k === "ac_working" || k === "heat_working") out.push({ label: FACT_LABELS[k], value: val === "yes" ? "Working" : "Not working", bad: val === "no" });
    else if (k === "water" || k === "power_on") out.push({ label: FACT_LABELS[k], value: val === "yes" ? "Yes" : "No", bad: val === "no" });
    else if (k === "unsafe_heating") { if (val === "yes") out.push({ label: FACT_LABELS[k], value: "Yes", bad: true }); }
    else out.push({ label: FACT_LABELS[k], value: val, bad: false });
  }
  return out;
}

export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`dots ${className}`} aria-label="Loading"><span /><span /><span /></span>;
}
