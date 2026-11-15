import { useEffect, useState } from "react";
import { Check, Phone, Snowflake, Sun } from "lucide-react";
import { api, type Hazard, type PersonDetail } from "./api";
import { Orb, Pill, Spinner, factTiles, time } from "./ui";

export default function PersonView({ id, onRemoved, refreshKey }: { id: string; onRemoved: () => void; refreshKey: number }) {
  const [p, setP] = useState<PersonDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [pick, setPick] = useState<Hazard | null>(null);

  useEffect(() => {
    let live = true;
    const load = () => api.person(id).then((d) => live && setP(d)).catch((e) => live && setError(e.message));
    load();
    const t = setInterval(load, 6000);
    return () => { live = false; clearInterval(t); };
  }, [id, refreshKey]);

  async function act(name: string, fn: () => Promise<unknown>, done: string) {
    setBusy(name); setNote(""); setError("");
    try { await fn(); setNote(done); setP(await api.person(id)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  if (!p) return <div className="flex h-40 items-center justify-center">{error ? <p className="text-[14px]">{error}</p> : <Spinner />}</div>;

  if (p.level === "pending") return <Consent p={p} busy={busy} note={note} error={error}
    retry={() => act("retry", () => api.retryConsent(p.id), `Calling ${p.first_name} again now.`)} />;

  const tiles = factTiles(p.facts);
  const autoHazard: Hazard = (p.weather?.alert?.hazard as Hazard) || (new Date().getMonth() >= 10 || new Date().getMonth() <= 2 ? "cold" : "heat");
  const checkHazard: Hazard = pick || autoHazard;

  return (
    <div className="fade-in flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <Orb level={p.level} size={60} />
        <div className="flex min-w-0 flex-col">
          <h2 className="serif truncate text-[36px] leading-none">{p.first_name}</h2>
          <span className="muted text-[14px]">{[p.relationship, p.city].filter(Boolean).join(" · ")}{p.last_call_at ? ` · checked ${time(p.last_call_at)}` : ""}</span>
        </div>
        <div className="ml-auto"><Pill level={p.level} /></div>
      </div>

      <p className="text-[16px] leading-relaxed">{p.headline}</p>

      {tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {tiles.map((t) => (
            <div key={t.label} className={`flex flex-col gap-0.5 rounded-[18px] p-3 ${t.bad ? "bg-[rgba(180,83,42,0.11)]" : "bg-[rgba(63,107,87,0.12)]"}`}>
              <span className="muted text-[12px]">{t.label}</span>
              <span className="font-semibold capitalize">{t.value}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 text-[13px]">
        {p.weather?.high_f != null && <span className="glass flex items-center gap-1.5 rounded-full px-3 py-1.5"><Sun size={14} />High {p.weather.high_f}°</span>}
        {p.weather?.low_f != null && <span className="glass flex items-center gap-1.5 rounded-full px-3 py-1.5"><Snowflake size={14} />Low {p.weather.low_f}°</span>}
        {p.weather?.alert && <span className="rounded-full bg-[rgba(180,83,42,0.12)] px-3 py-1.5 font-semibold text-[#9A4321]">{p.weather.alert.event}</span>}
      </div>

      {p.timeline.length > 0 && (
        <section className="flex flex-col gap-2.5">
          <h3 className="eyebrow">Recent</h3>
          <ol className="flex flex-col gap-2.5 text-[14px]">
            {p.timeline.slice(0, 6).map((t, i) => (
              <li key={i} className="flex gap-3.5">
                <span className="muted w-[92px] shrink-0">{time(t.at)}</span>
                <span className={t.kind === "scheduled" ? "font-semibold" : ""}>{t.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="glass flex flex-col gap-3 rounded-[24px] p-4">
        <h3 className="eyebrow">If {p.first_name} needs help</h3>
        {p.contacts.map((c) => (
          <div key={c.order} className="flex items-center gap-3 text-[14px]">
            <span className={`flex h-7 w-7 items-center justify-center rounded-full text-[13px] font-semibold ${c.order === 1 ? "bg-[var(--ink)] text-white" : "bg-white/70"}`}>{c.order}</span>
            <span><strong>{c.is_you ? "You" : c.name}</strong> · {c.role}</span>
          </div>
        ))}
        <p className="muted text-[13px]">For signs of an emergency, we tell {p.first_name} to call 911 and alert everyone above at once.</p>
      </section>

      {note && <p className="rounded-2xl bg-[rgba(63,107,87,0.12)] px-4 py-3 text-[14px] text-[#2B4D40]" role="status">{note}</p>}
      {error && <p className="rounded-2xl bg-[rgba(180,83,42,0.1)] px-4 py-3 text-[14px] text-[#8A3B1C]" role="alert">{error}</p>}

      <div className="grid grid-cols-2 gap-2">
        {p.status === "active" && !p.paused && (
          <div className="col-span-2 flex items-center gap-2 text-[14px]" role="radiogroup" aria-label="Kind of check-in">
            <span className="muted">Check for</span>
            {(["heat", "cold"] as Hazard[]).map((h) => (
              <button key={h} role="radio" aria-checked={checkHazard === h} onClick={() => setPick(h)}
                className={`flex h-10 items-center gap-1.5 rounded-full px-4 font-semibold ${checkHazard === h ? "bg-[var(--ink)] text-white" : "bg-white/60"}`}>
                {h === "heat" ? <Sun size={15} /> : <Snowflake size={15} />}{h === "heat" ? "Heat" : "Cold"}
              </button>
            ))}
          </div>
        )}
        {p.status === "active" && !p.paused && (
          <button className="btn-ink col-span-2 flex h-12 items-center justify-center gap-2" disabled={!!busy}
            onClick={() => act("check", () => api.checkNow(p.id, checkHazard), `Calling ${p.first_name} now for a ${checkHazard} check-in.`)}>
            <Phone size={17} />{busy === "check" ? "Calling…" : `Check on ${p.first_name} now`}
          </button>
        )}
        {p.status === "active" && (
          <button className="btn-soft h-12" disabled={!!busy}
            onClick={() => act("pause", () => api.pause(p.id, !p.paused), p.paused ? "Calls are back on." : "Calls are paused.")}>
            {p.paused ? "Resume calls" : "Pause calls"}
          </button>
        )}
        <button className="btn-soft h-12" disabled={!!busy}
          onClick={() => { if (confirm(`Stop looking after ${p.first_name}? We won't call them again.`)) act("remove", () => api.remove(p.id).then(onRemoved), "Removed."); }}>
          Remove
        </button>
      </div>
    </div>
  );
}

function Consent({ p, busy, note, error, retry }: { p: PersonDetail; busy: string; note: string; error: string; retry: () => void }) {
  const noAnswer = p.status === "consent_no_answer";
  const step = (done: boolean, active: boolean, title: string, sub: string, last = false) => (
    <li className="flex gap-3.5">
      <div className="flex flex-col items-center">
        <span className={`flex h-7 w-7 items-center justify-center rounded-full ${done ? "bg-[#3F6B57]" : active ? "border-2 border-[var(--accent)] bg-white" : "border-2 border-[#C9C4D2] bg-white"}`}>
          {done ? <Check size={16} color="#fff" strokeWidth={3} /> : active ? <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent)]" /> : null}
        </span>
        {!last && <span className={`h-9 w-0.5 ${done ? "bg-[#3F6B57]" : "bg-[#D5D0DC]"}`} />}
      </div>
      <div className="flex flex-col pt-0.5"><span className="text-[15px] font-semibold">{title}</span><span className="muted text-[13px]">{sub}</span></div>
    </li>
  );
  return (
    <div className="fade-in flex flex-col gap-5">
      <div className="flex items-center gap-4">
        <Orb level="pending" size={60} />
        <div>
          <h2 className="serif text-[34px] leading-none">{noAnswer ? `${p.first_name} didn't pick up` : `We're asking ${p.first_name}`}</h2>
          <span className="muted text-[14px]">{[p.relationship, p.city].filter(Boolean).join(" · ")}</span>
        </div>
      </div>
      <p className="text-[16px] leading-relaxed">
        We'll tell {p.first_name} you signed them up and ask if it's okay to call on dangerous heat or cold days.
        If they say no, we won't call again.
      </p>
      <ol className="flex flex-col">
        {step(true, false, `Added ${p.first_name}`, "Done")}
        {step(false, true, noAnswer ? "No answer to the permission call" : "Asking permission", `Calls come from (959) 208-4166 in ${p.language === "es" ? "Spanish" : "English"}`)}
        {step(false, false, "Check-ins start", "On the next heat or cold warning", true)}
      </ol>
      <div className="glass rounded-[20px] p-4 text-[14px] leading-snug">
        Tip: let {p.first_name} know a call is coming from <strong>(959) 208-4166</strong> so they pick up.
      </div>
      {note && <p className="rounded-2xl bg-[rgba(63,107,87,0.12)] px-4 py-3 text-[14px]" role="status">{note}</p>}
      {error && <p className="rounded-2xl bg-[rgba(180,83,42,0.1)] px-4 py-3 text-[14px] text-[#8A3B1C]" role="alert">{error}</p>}
      <button className="btn-ink h-12" onClick={retry} disabled={!!busy}>{busy ? "Calling…" : noAnswer ? `Call ${p.first_name} again` : "Call again now"}</button>
    </div>
  );
}
