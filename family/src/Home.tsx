import { Plus } from "lucide-react";
import type { Hazard, Me, Person } from "./api";
import { Orb, Pill, greeting, minutesUntil, time } from "./ui";

export function ModeSwitch({ mode, setMode, large = false }: { mode: Hazard; setMode: (m: Hazard) => void; large?: boolean }) {
  const btn = (m: Hazard, label: string) => (
    <button
      type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
      className={`rounded-full ${large ? "px-4 py-2 text-[14px]" : "px-3 py-1.5 text-[13px]"} transition ${mode === m ? "bg-white font-semibold text-[var(--accent)] shadow-sm" : "font-medium text-[var(--muted)]"}`}
    >{label}</button>
  );
  return (
    <div className="glass flex gap-0.5 rounded-full p-1" role="group" aria-label="Weather mode">
      {btn("heat", "Heat")}{btn("cold", "Cold")}
    </div>
  );
}

/** The big number: today's high (heat) or tonight's low (cold) where your people live. */
export function Hero({ me, mode, large = false }: { me: Me; mode: Hazard; large?: boolean }) {
  const withWx = me.people.filter((p) => p.weather && (mode === "heat" ? p.weather.high_f != null : p.weather.low_f != null));
  const pick = withWx.sort((a, b) => mode === "heat"
    ? (b.weather.high_f ?? -99) - (a.weather.high_f ?? -99)
    : (a.weather.low_f ?? 999) - (b.weather.low_f ?? 999))[0];
  const alertP = me.people.find((p) => p.weather?.alert?.hazard === mode);
  const temp = pick ? (mode === "heat" ? pick.weather.high_f : pick.weather.low_f) : null;
  const first = (me.user.name || "").split(" ")[0];
  return (
    <div className="flex flex-col gap-1.5">
      <span className="muted text-[15px] lg:text-[17px]">{greeting()}{first ? `, ${first}` : ""}</span>
      <div className="flex items-end gap-3">
        <span className={`serif leading-[0.85] tracking-[-0.04em] ${large ? "text-[184px]" : "text-[132px]"}`}>
          {temp != null ? `${temp}°` : "—"}
        </span>
        {pick && (
          <span className="muted pb-4 text-[14px] leading-snug lg:pb-6 lg:text-[16px]">
            {mode === "heat" ? "high today" : "low tonight"}<br />in {pick.city || "their area"}
          </span>
        )}
      </div>
      <span className="glass mt-2.5 self-start rounded-full px-3.5 py-2 text-[13px] font-medium">
        {alertP?.weather.alert
          ? `${alertP.weather.alert.event} · ${alertP.city || ""}`
          : mode === "heat" ? "No heat warnings right now" : "No cold warnings right now"}
      </span>
    </div>
  );
}

export function PersonCard({ p, onOpen, selected }: { p: Person; onOpen: () => void; selected?: boolean }) {
  const mins = minutesUntil(p.next_call_at);
  const sub = p.level === "pending" ? "Waiting for their yes"
    : p.last_call_at ? `Last call ${time(p.last_call_at)}` : p.city || "";
  return (
    <button
      type="button" onClick={onOpen}
      className={`glass fade-in flex w-full flex-col gap-3.5 rounded-[28px] p-4 text-left transition hover:bg-white/60 lg:p-5 ${selected ? "ring-2 ring-[var(--ink)]/20" : ""}`}
    >
      <div className="flex w-full items-center gap-3.5">
        <Orb level={p.level} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[17px] font-semibold">{p.first_name}{p.relationship ? <span className="muted font-normal"> · {p.relationship}</span> : null}</span>
          <span className="muted truncate text-[14px]">{sub}</span>
        </div>
        <Pill level={p.level} />
      </div>
      {(p.level === "warning" || p.level === "emergency" || p.level === "no_answer") && (
        <p className="line-clamp-2 text-[14px] leading-snug">{p.headline}</p>
      )}
      {mins != null && (
        <div className="flex w-full flex-col gap-2">
          <div className="h-1.5 overflow-hidden rounded-full bg-[rgba(38,33,46,0.08)]">
            <div className="h-full rounded-full bg-[#D9774D]" style={{ width: `${Math.max(6, 100 - Math.min(100, (mins / 30) * 100))}%` }} />
          </div>
          <span className="muted text-[13px]">We'll call {p.first_name} back {mins <= 1 ? "in a moment" : `in ${mins} min`}</span>
        </div>
      )}
    </button>
  );
}

export function EmptyPeople({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="glass flex flex-col items-start gap-3 rounded-[28px] p-6">
      <span className="serif text-[28px] leading-tight">Who should we look after?</span>
      <p className="muted text-[15px]">Tell the assistant about your mom, dad or grandparent. It takes about a minute.</p>
      <button className="btn-ink mt-1 flex h-12 items-center gap-2 px-5" onClick={onAdd}><Plus size={18} />Add someone</button>
    </div>
  );
}
