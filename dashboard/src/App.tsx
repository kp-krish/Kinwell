import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ChevronLeft, Globe2, HardHat, List, Loader2, Lock, Map as MapIcon, Phone, PhoneCall,
  RefreshCw, Snowflake, Sparkles, Sun, Users,
} from "lucide-react";
import { api, ago, clock, type Alert, type Briefing, type Checkin, type Resident, type State } from "./api";
import MapView from "./MapView";
import { STATUS_META, latestByResident, statusOf, type Status } from "./status";

type View = "now" | "map" | "people" | "crews" | "resources";
const VIEWS: { id: View; label: string; short: string; icon: React.ReactNode }[] = [
  { id: "now", label: "Right now", short: "Needs you", icon: <AlertTriangle size={18} /> },
  { id: "map", label: "Map", short: "Map", icon: <MapIcon size={18} /> },
  { id: "people", label: "People", short: "Everyone", icon: <Users size={18} /> },
  { id: "crews", label: "Crews", short: "Crews", icon: <HardHat size={18} /> },
  { id: "resources", label: "Cooling & warming", short: "Places", icon: <Globe2 size={18} /> },
];

interface Hazard { hazard: "heat" | "cold"; label: string; temp?: string; place?: string; live: boolean }

export default function App() {
  const [state, setState] = useState<State | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>("now");
  const [selected, setSelected] = useState<Checkin | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingBusy, setBriefingBusy] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    try { setState(await api.state()); setErr(null); } catch (e) { setErr(String(e)); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => { load(); setNow(Date.now()); }, 3000);
    return () => clearInterval(t);
  }, [load]);

  const latest = useMemo(() => latestByResident(state?.checkins || []), [state]);
  const residents = useMemo(() => state?.residents || [], [state]);
  const openAlerts = useMemo(() => (state?.alerts || []).filter((a) => !a.resolved_at), [state]);
  const alertFor = useMemo(() => {
    const m = new Map<string, Alert>();
    for (const a of openAlerts) if (!m.has(a.resident_id)) m.set(a.resident_id, a);
    return m;
  }, [openAlerts]);

  const hazard = useMemo<Hazard>(() => deriveHazard(state, now), [state, now]);
  useEffect(() => { document.documentElement.dataset.hazard = hazard.hazard; }, [hazard.hazard]);

  const lanes = useMemo(() => {
    const need: Resident[] = [], handling: Resident[] = [], safe: Resident[] = [], notYet: Resident[] = [];
    const rank: Status[] = ["emergency", "warning", "no_answer", "calling", "pending", "safe"];
    const sorted = [...residents].sort((a, b) => rank.indexOf(statusOf(a, latest.get(a._id))) - rank.indexOf(statusOf(b, latest.get(b._id))));
    for (const r of sorted) {
      const st = statusOf(r, latest.get(r._id));
      if (st === "emergency" || st === "warning" || (alertFor.has(r._id) && st !== "calling")) need.push(r);
      else if (st === "calling" || st === "no_answer" || ["pending_consent", "consent_no_answer"].includes(r.status || "")) handling.push(r);
      else if (st === "safe") safe.push(r);
      else notYet.push(r);
    }
    return { need, handling, safe, notYet };
  }, [residents, latest, alertFor]);

  const openCheckin = async (id: string) => {
    try { setSelected(await api.checkin(id)); } catch (e) { setErr(String(e)); }
  };
  const onSelectResident = useCallback((r: Resident) => {
    const c = latestByResident(state?.checkins || []).get(r._id);
    if (c) openCheckin(c._id);
  }, [state]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    try { await fn(); await load(); } catch (e) { setErr(String(e)); } finally { setBusy(null); }
  };
  const loadBriefing = async () => {
    setBriefingBusy(true);
    try { setBriefing(await api.briefing()); } catch (e) { setErr(String(e)); } finally { setBriefingBusy(false); }
  };

  const act = { now, busy, latest, alertFor, onOpen: openCheckin,
    onCall: (id: string) => run("call" + id, () => api.call(id)),
    onAck: (id: string) => run("ack" + id, () => api.ack(id)) };

  return (
    <div className="relative min-h-screen font-sans">
      <div className="backdrop" aria-hidden="true" />
      <div className="relative z-10 mx-auto flex max-w-[1440px] flex-col gap-5 px-4 pb-28 safe-top sm:px-7 md:pb-10">
        <Header view={view} setView={setView} hazard={hazard} busy={busy}
          onHeat={() => run("simulate", api.simulate)} onCold={() => run("simulateCold", api.simulateCold)} />

        {err && <div className="rounded-2xl bg-ember/15 px-4 py-2 text-sm text-[#FFD2CB] ring-1 ring-ember/40">Connection problem: {err.slice(0, 160)}</div>}

        {view === "now" && (
          <>
            <Hero hazard={hazard} lanes={lanes} busy={busy}
              onHeat={() => run("simulate", api.simulate)} onCold={() => run("simulateCold", api.simulateCold)} />
            <BriefingBar briefing={briefing} busy={briefingBusy} onLoad={loadBriefing} />
            <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
              <Lane title="Need you" tone="text-[#FFB3A9]" empty="Nobody needs a human call right now.">
                {lanes.need.map((r) => <NeedCard key={r._id} r={r} c={latest.get(r._id)} a={alertFor.get(r._id)} {...act} />)}
              </Lane>
              <Lane title="Kinwell is handling" tone="text-ice-soft" empty="No calls in progress.">
                {lanes.handling.map((r) => <HandlingRow key={r._id} r={r} c={latest.get(r._id)} now={now} onOpen={openCheckin} />)}
              </Lane>
              <Lane title={hazard.hazard === "cold" ? "Warm and safe" : "Cool and safe"} tone="text-[#B7E4C6]"
                empty="No completed check-ins yet." className="md:col-span-2 xl:col-span-1">
                <SafeList people={lanes.safe} latest={latest} now={now} onOpen={openCheckin} hazard={hazard.hazard} />
                {lanes.notYet.length > 0 && (
                  <p className="px-1.5 pt-1 text-sm text-haze">{lanes.notYet.length} more not called yet today.</p>
                )}
                <PlacesNote state={state} hazard={hazard.hazard} now={now} />
              </Lane>
            </div>
          </>
        )}

        {view === "map" && (
          <section className="glass relative h-[calc(100vh-190px)] min-h-[420px] overflow-hidden rounded-[26px]">
            <MapView residents={residents} latest={latest} resources={state?.resources || []} onSelect={onSelectResident} />
            <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-2xl bg-ink/85 px-3 py-2 text-xs text-mist">
              {(["emergency", "warning", "calling", "safe"] as Status[]).map((s) => (
                <span key={s} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_META[s].color }} />{STATUS_META[s].label}</span>
              ))}
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-ice" />Cooling center</span>
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#F4A47C]" />Warming center</span>
              <span>· hover a center for details</span>
              <span>· square = crew worker</span>
            </div>
          </section>
        )}

        {view === "people" && (
          <section className="glass rounded-[26px] p-3 sm:p-4">
            <h2 className="px-2 pb-2 pt-1 text-lg font-semibold">Everyone <span className="font-normal text-haze">· {residents.length}</span></h2>
            <PeopleList people={residents} {...act} />
          </section>
        )}

        {view === "crews" && <CrewView state={state} {...act} onStartShift={(cid) => run("shift" + cid, () => api.startShift(cid))} />}

        {view === "resources" && <Resources state={state} now={now} busy={busy} onRefresh={() => run("scout", api.refreshScout)} />}
      </div>

      <MobileNav view={view} setView={setView} badge={lanes.need.length} />
      {selected && <CheckinPanel c={selected} alerts={(state?.alerts || []).filter((a) => a.resident_id === selected.resident_id)}
        person={residents.find((r) => r._id === selected.resident_id)} onClose={() => setSelected(null)}
        onCall={() => act.onCall(selected.resident_id)} busy={busy} />}
    </div>
  );
}

function deriveHazard(state: State | null, now: number): Hazard {
  const recent = (state?.checkins || [])
    .filter((c) => c.context?.hazard && c.purpose !== "consent" && now - new Date(c.started_at).getTime() < 12 * 3600_000)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
  if (recent?.context?.hazard) {
    const h = recent.context.hazard;
    const t = h === "cold" ? recent.context.low_f : recent.context.high_f;
    const person = state?.residents.find((r) => r._id === recent.resident_id);
    return { hazard: h, label: recent.context.alert_type || (h === "cold" ? "Cold warning" : "Heat warning"),
      temp: t != null && t !== "unknown" ? String(t).replace("-", "−") : undefined, place: person?.city, live: true };
  }
  const nws = (state?.weather_alerts || []).find((a) => a.calls) || (state?.weather_alerts || [])[0];
  if (nws) return { hazard: nws.hazard, label: "NWS " + nws.event, live: nws.calls };
  const m = new Date(now).getMonth();
  return { hazard: m >= 10 || m <= 2 ? "cold" : "heat", label: "No weather warnings right now", live: false };
}

function Logo({ sub }: { sub?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <img src="/icon.svg" alt="" className="h-7 w-7" />
      <span className="font-serif text-[26px] italic leading-none">Kinwell</span>
      {sub && <span className="hidden text-[11px] font-semibold uppercase tracking-[0.14em] text-haze sm:inline">{sub}</span>}
    </div>
  );
}

function Header({ view, setView, hazard, busy, onHeat, onCold }: {
  view: View; setView: (v: View) => void; hazard: Hazard; busy: string | null; onHeat: () => void; onCold: () => void;
}) {
  const hour = new Date().getHours();
  const shift = hour >= 19 || hour < 7 ? "Team · night shift" : "Team · day shift";
  return (
    <header className="flex flex-wrap items-center gap-4 pt-1">
      <Logo sub={shift} />
      <nav aria-label="Main" className="ml-2 hidden gap-1 rounded-full bg-white/[0.06] p-1 md:flex">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)} aria-current={view === v.id ? "page" : undefined}
            className={`h-9 rounded-full px-3.5 text-sm transition ${view === v.id ? "bg-white/15 font-semibold text-white" : "font-medium text-[#D9D3E4] hover:bg-white/[0.07]"}`}>
            {v.label}
          </button>
        ))}
      </nav>
      <div className="ml-auto hidden items-center gap-2 lg:flex">
        <SimButtons busy={busy} onHeat={onHeat} onCold={onCold} />
      </div>
      <span className="ml-auto text-xs font-semibold text-haze md:hidden">{hazard.live ? "You're on call" : "All quiet"}</span>
    </header>
  );
}

function SimButtons({ busy, onHeat, onCold }: { busy: string | null; onHeat: () => void; onCold: () => void }) {
  const cls = "inline-flex h-10 items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 text-sm font-semibold text-white hover:bg-white/[0.12] disabled:opacity-50";
  return (
    <>
      <button onClick={onHeat} disabled={!!busy} className={cls}>
        {busy === "simulate" ? <Loader2 size={15} className="animate-spin" /> : <Sun size={15} className="text-[#F4A47C]" />} Simulate heat
      </button>
      <button onClick={onCold} disabled={!!busy} className={cls}>
        {busy === "simulateCold" ? <Loader2 size={15} className="animate-spin" /> : <Snowflake size={15} className="text-ice" />} Simulate cold
      </button>
    </>
  );
}

function Hero({ hazard, lanes, busy, onHeat, onCold }: {
  hazard: Hazard; lanes: { need: Resident[]; handling: Resident[]; safe: Resident[] }; busy: string | null; onHeat: () => void; onCold: () => void;
}) {
  const cold = hazard.hazard === "cold";
  const chip = cold ? "bg-ice/15 text-ice-soft" : "bg-[#F4A47C]/15 text-[#FCD3BC]";
  const n = lanes.need.length;
  return (
    <section className="flex flex-wrap items-end gap-5 md:gap-7">
      <div className="flex min-w-0 flex-col gap-2">
        <span className={`inline-flex h-8 items-center gap-2 self-start rounded-full px-3.5 text-[13px] font-semibold ${chip}`}>
          {cold ? <Snowflake size={14} /> : <Sun size={14} />}{hazard.label}
        </span>
        {hazard.temp ? (
          <h1 className="m-0 font-serif text-[76px] font-normal leading-[0.88] tracking-[-0.04em] sm:text-[120px]">
            {hazard.temp}°<span className="text-[28px] italic tracking-[-0.01em] text-haze sm:text-[44px]"> {cold ? "low tonight" : "high today"}{hazard.place ? `, ${hazard.place}` : ""}</span>
          </h1>
        ) : (
          <h1 className="m-0 font-serif text-[44px] font-normal leading-none tracking-[-0.02em] sm:text-[64px]">
            {n ? <>{n} {n === 1 ? "person needs" : "people need"} <i>a human</i></> : <>Everyone's <i>okay</i> right now</>}
          </h1>
        )}
      </div>
      <div className="flex w-full gap-2 sm:ml-auto sm:w-auto sm:gap-2.5">
        <Count n={lanes.need.length} label="Need you" color="text-ember" />
        <Count n={lanes.handling.length} label={<><span className="sm:hidden">Handling</span><span className="hidden sm:inline">Kinwell handling</span></>} color="text-ice" />
        <Count n={lanes.safe.length} label={cold ? "Warm" : "Safe"} color="text-leaf" />
      </div>
      <div className="flex w-full flex-wrap gap-2 lg:hidden"><SimButtons busy={busy} onHeat={onHeat} onCold={onCold} /></div>
    </section>
  );
}

function Count({ n, label, color }: { n: number; label: React.ReactNode; color: string }) {
  return (
    <div className="glass min-w-0 flex-1 rounded-[20px] px-3.5 py-3 sm:min-w-[124px] sm:flex-none sm:px-4.5">
      <div className={`num font-serif text-[34px] leading-none sm:text-[40px] ${color}`}>{n}</div>
      <div className="truncate text-[13px] font-semibold">{label}</div>
    </div>
  );
}

function BriefingBar({ briefing, busy, onLoad }: { briefing: Briefing | null; busy: boolean; onLoad: () => void }) {
  return (
    <section className="glass flex flex-col gap-3 rounded-[22px] px-4 py-3.5 sm:px-5">
      <div className="flex flex-wrap items-center gap-3">
        <Sparkles size={16} className="text-[#E6C9F5]" />
        <span className="text-sm font-semibold">{briefing ? briefing.headline : "Who should a person call first?"}</span>
        {!briefing && <span className="hidden text-sm text-haze sm:inline">Gemini ranks today's check-ins.</span>}
        <button onClick={onLoad} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-4 text-[13px] font-bold text-ink hover:bg-white/90">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} {briefing ? "Re-rank" : "Rank now"}
        </button>
      </div>
      {briefing && (
        <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {[...briefing.items].sort((a, b) => a.priority - b.priority).map((i) => (
            <li key={i.resident_id} className="flex gap-2.5 rounded-2xl bg-white/[0.05] px-3 py-2.5 text-sm">
              <span className="num grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/15 text-xs font-bold">{i.priority}</span>
              <span className="text-[#E4DEEC]"><b className="text-white">{i.name}</b>: {i.reason}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Lane({ title, tone, empty, className = "", children }: { title: string; tone: string; empty: string; className?: string; children: React.ReactNode }) {
  const kids = Array.isArray(children) ? children.flat().filter(Boolean) : children ? [children] : [];
  return (
    <section aria-label={title} className={`glass flex flex-col gap-2.5 rounded-[26px] p-3.5 sm:p-4 ${className}`}>
      <h2 className={`mx-1 mb-0.5 text-[13px] font-semibold uppercase tracking-[0.12em] ${tone}`}>{title}</h2>
      {kids.length ? children : <p className="px-1.5 pb-1 text-sm text-haze">{empty}</p>}
    </section>
  );
}

function Chip({ s, text }: { s: Status; text?: string }) {
  return <span className={`shrink-0 rounded-[10px] px-2.5 py-0.5 text-xs font-bold ${STATUS_META[s].chip}`}>{text || STATUS_META[s].label}</span>;
}

function summaryOf(c?: Checkin, a?: Alert) {
  return c?.case_note?.summary || a?.reason || c?.risk_reasons?.join(", ") || (c ? c.call_status.replace("_", " ") : "");
}

type Act = {
  now: number; busy: string | null; latest: Map<string, Checkin>; alertFor: Map<string, Alert>;
  onOpen: (id: string) => void; onCall: (id: string) => void; onAck: (id: string) => void;
};

function NeedCard({ r, c, a, now, busy, onOpen, onCall, onAck }: { r: Resident; c?: Checkin; a?: Alert } & Act) {
  const st = statusOf(r, c);
  const hot = st === "emergency";
  const btn = "inline-flex h-10 items-center gap-1.5 rounded-full px-4 text-[13px] font-semibold";
  return (
    <article className={`flex flex-col gap-2 rounded-[20px] p-4 ${hot ? "border border-ember/40 bg-ember/[0.14]" : "bg-white/[0.06]"}`}>
      <div className="flex items-center gap-2">
        <span className="min-w-0 truncate text-base font-bold">{r.name}</span>
        {r.playbook === "crew" && <span className="text-xs text-haze">· {r.crew_name || "crew"}</span>}
        <span className="ml-auto"><Chip s={st} text={st === "no_answer" ? "No answer" : undefined} /></span>
      </div>
      <p className="m-0 text-sm leading-relaxed text-[#E4DEEC]">{summaryOf(c, a)}</p>
      <div className="text-xs text-mist">
        {ago(c?.started_at || a?.created_at, now)}
        {a && <> · {a.notified?.length ? <>told {a.notified.join(", ")}</> : "no contact reached yet"}</>}
        {c?.callback_at && new Date(c.callback_at).getTime() > now && <> · callback {clock(c.callback_at)}</>}
      </div>
      <div className="flex flex-wrap gap-2">
        {c && <button onClick={() => onOpen(c._id)} className={`${btn} ${hot ? "bg-white text-ink" : "bg-white/90 text-ink"} hover:bg-white`}>Open call</button>}
        {r.phone && (
          <button onClick={() => onCall(r._id)} className={`${btn} border border-white/25 text-white hover:bg-white/10`}>
            {busy === "call" + r._id ? <Loader2 size={14} className="animate-spin" /> : <Phone size={14} />} Call again
          </button>
        )}
        {a && (
          <button onClick={() => onAck(a._id)} className={`${btn} border border-white/25 text-white hover:bg-white/10`}>
            {busy === "ack" + a._id && <Loader2 size={14} className="animate-spin" />} Acknowledge
          </button>
        )}
      </div>
    </article>
  );
}

function HandlingRow({ r, c, now, onOpen }: { r: Resident; c?: Checkin; now: number; onOpen: (id: string) => void }) {
  const st = statusOf(r, c);
  const live = st === "calling";
  const consent = ["pending_consent", "consent_no_answer"].includes(r.status || "");
  const line = live ? `On a call · ${c?.call_status === "dialing" ? "dialing" : "talking"}${c?.attempt ? ` · attempt ${c.attempt + 1}` : ""}`
    : consent ? `Waiting to say yes to calls${r.enrolled_by ? ` · enrolled by ${r.enrolled_by.replace(/, a family member$/, "")}` : ""}`
    : `No answer${c?.callback_at ? ` · retrying at ${clock(c.callback_at)}` : ""} · ${ago(c?.started_at, now)}`;
  return (
    <button onClick={() => c && onOpen(c._id)} className="flex items-center gap-3 rounded-[20px] bg-white/[0.06] px-4 py-3.5 text-left hover:bg-white/[0.09]">
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${live ? "live-dot bg-ice" : "border-2 border-ice"}`} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold">{r.name}</span>
        <span className="block truncate text-[13px] text-mist">{line}</span>
      </span>
    </button>
  );
}

function SafeList({ people, latest, onOpen, hazard }: { people: Resident[]; latest: Map<string, Checkin>; now: number; onOpen: (id: string) => void; hazard: "heat" | "cold" }) {
  if (!people.length) return null;
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {people.slice(0, 8).map((r) => {
        const c = latest.get(r._id);
        const detail = c?.context?.hazard === "cold" || hazard === "cold"
          ? [c?.heat_working === "yes" ? "Heat on" : null, c?.indoor_temp].filter(Boolean).join(" · ")
          : [c?.ac_working === "yes" ? "AC on" : null, c?.water ? `water ${c.water}` : null].filter(Boolean).join(" · ");
        return (
          <li key={r._id} className="border-b border-white/[0.08] last:border-0">
            <button onClick={() => c && onOpen(c._id)} className="flex w-full justify-between gap-3 px-1.5 py-2.5 text-left text-sm hover:text-white">
              <span className="truncate font-semibold">{r.name}</span>
              <span className="num shrink-0 text-mist">{detail ? `${detail} · ` : ""}{clock(c?.started_at)}</span>
            </button>
          </li>
        );
      })}
      {people.length > 8 && <li className="px-1.5 py-2 text-sm text-mist">+ {people.length - 8} more</li>}
    </ul>
  );
}

function PlacesNote({ state, hazard, now }: { state: State | null; hazard: "heat" | "cold"; now: number }) {
  const type = hazard === "cold" ? "warming_center" : "cooling_center";
  const places = (state?.resources || []).filter((r) => r.type === type);
  if (!places.length) return null;
  const fetched = places.map((p) => p.fetched_at || "").sort().pop();
  return (
    <div className="mt-1 flex flex-col gap-1 rounded-[18px] bg-ice/10 p-3.5">
      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-ice-soft">{hazard === "cold" ? "Warming centers" : "Cooling centers"} on file</span>
      <span className="text-sm">{places.slice(0, 2).map((p) => p.name).join(" · ")}{places.length > 2 ? ` · +${places.length - 2}` : ""}</span>
      {fetched && <span className="text-xs text-mist">Hours checked {clock(fetched)} ({ago(fetched, now)}) by Resource Scout</span>}
    </div>
  );
}

function PeopleList({ people, latest, now, onOpen, onCall, busy }: { people: Resident[] } & Act) {
  const order: Status[] = ["emergency", "warning", "no_answer", "calling", "pending", "safe"];
  const sorted = [...people].sort((a, b) => order.indexOf(statusOf(a, latest.get(a._id))) - order.indexOf(statusOf(b, latest.get(b._id))));
  return (
    <ul className="m-0 list-none divide-y divide-white/[0.07] p-0">
      {sorted.map((r) => {
        const c = latest.get(r._id);
        const st = statusOf(r, c);
        return (
          <li key={r._id} className="flex items-center gap-3 px-2 py-3">
            <button onClick={() => c && onOpen(c._id)} className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-2">
                <span className="truncate font-semibold">{r.name}</span>
                {r.playbook === "crew" && <HardHat size={13} className="shrink-0 text-haze" />}
                <Chip s={st} />
              </div>
              <div className="truncate text-[13px] text-mist">
                {c ? <>{summaryOf(c)} · {ago(c.started_at, now)}</> : [r.city, ...(r.risk_factors || [])].filter(Boolean).join(" · ")}
              </div>
            </button>
            {r.phone && (
              <button aria-label={`Call ${r.name} now`} onClick={() => onCall(r._id)} className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/15 hover:bg-white/10">
                {busy === "call" + r._id ? <Loader2 size={15} className="animate-spin" /> : <Phone size={15} />}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function CrewView({ state, onStartShift, ...act }: { state: State | null; onStartShift: (crewId: string) => void } & Act) {
  const crews = state?.crews || [];
  if (!crews.length) return <section className="glass rounded-[26px] p-5 text-sm text-haze">No crews enrolled.</section>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {crews.map((crew) => {
        const workers = (state?.residents || []).filter((r) => r.crew_id === crew._id);
        const log = (state?.checkins || []).filter((c) => workers.some((w) => w._id === c.resident_id)).slice(0, 8);
        return (
          <section key={crew._id} className="glass flex flex-col gap-3 rounded-[26px] p-4 sm:p-5">
            <div className="flex flex-wrap items-center gap-2">
              <HardHat size={16} className="text-[#F4A47C]" />
              <h2 className="text-base font-bold">{crew.employer} <span className="font-normal text-haze">· {crew.name}</span></h2>
              <span className="text-xs text-mist sm:ml-auto">Shift {crew.shift_start}–{crew.shift_end}, every {crew.interval_min / 60} h</span>
            </div>
            <button onClick={() => onStartShift(crew._id)} className="inline-flex h-10 items-center gap-2 self-start rounded-full bg-white px-4 text-[13px] font-bold text-ink hover:bg-white/90">
              {act.busy === "shift" + crew._id ? <Loader2 size={14} className="animate-spin" /> : <PhoneCall size={14} />} Start shift check-ins
            </button>
            <PeopleList people={workers} {...act} />
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-haze">Shift log</div>
              <ul className="m-0 list-none p-0 text-[13px] text-[#E4DEEC]">
                {log.length === 0 && <li className="text-haze">No check-ins this shift yet.</li>}
                {log.map((c) => (
                  <li key={c._id} className="flex gap-3 py-0.5">
                    <span className="num w-16 shrink-0 text-haze">{clock(c.started_at)}</span>
                    <span className="truncate">{c.resident_name}: {c.call_status === "no_answer" ? "missed check-in" :
                      c.risk_level === "clear" ? "checked in" : (c.risk_reasons?.join(", ") || c.call_status)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <p className="flex items-center gap-1.5 text-xs text-haze"><Lock size={12} /> Supervisors see answers only when a red flag or missed check-in fires.</p>
          </section>
        );
      })}
    </div>
  );
}

function Resources({ state, now, busy, onRefresh }: { state: State | null; now: number; busy: string | null; onRefresh: () => void }) {
  const places = (state?.resources || []).filter((r) => r.type === "cooling_center" || r.type === "warming_center");
  const programs = (state?.resources || []).filter((r) => !places.includes(r));
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1fr_420px]">
      <section className="glass rounded-[26px] p-3 sm:p-4">
        <h2 className="px-2 pb-2 pt-1 text-lg font-semibold">Places people can go</h2>
        <ul className="m-0 list-none divide-y divide-white/[0.07] p-0">
          {places.map((p) => (
            <li key={p._id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-2 py-3">
              <span className="font-semibold">{p.name}</span>
              <span className={`rounded-[10px] px-2 py-0.5 text-xs font-bold ${p.type === "warming_center" ? "bg-ice/20 text-ice-soft" : "bg-[#F4A47C]/20 text-[#FCD3BC]"}`}>{p.type === "warming_center" ? "Warming" : "Cooling"}</span>
              <span className="w-full text-[13px] text-mist">{p.hours_today || "hours unknown"} · {p.address}{p.source_url === "seed" ? " · seed data" : ""}</span>
            </li>
          ))}
        </ul>
        {programs.length > 0 && (
          <>
            <h3 className="px-2 pb-1 pt-4 text-xs font-semibold uppercase tracking-[0.12em] text-haze">Help programs</h3>
            <ul className="m-0 list-none p-0">{programs.map((p) => <li key={p._id} className="px-2 py-1.5 text-sm">{p.name}</li>)}</ul>
          </>
        )}
      </section>
      <section className="glass flex flex-col gap-2 rounded-[26px] p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <Globe2 size={16} className="text-ice" /><h2 className="text-base font-bold">Resource Scout</h2>
          <button onClick={onRefresh} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-4 text-[13px] font-bold text-ink">
            {busy === "scout" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Refresh
          </button>
        </div>
        <p className="text-xs text-haze">TinyFish web agent on Maritime → Atlas. The voice agent quotes only these records.</p>
        {(state?.scout_runs || []).slice(0, 3).map((r) => (
          <details key={r._id} className="rounded-2xl bg-white/[0.05] px-3 py-2 text-xs">
            <summary className="cursor-pointer">
              <span className={r.status === "ok" ? "text-leaf" : r.status === "running" ? "text-ice" : "text-ember"}>●</span>{" "}
              {r.source} · {r.status}{r.sites_saved != null ? ` · ${r.sites_saved} saved` : ""} · {clock(r.started_at)} ({ago(r.started_at, now)})
            </summary>
            <ul className="mt-1 list-none space-y-0.5 p-0 font-mono text-[11px] text-mist">
              {r.log.map((l, i) => <li key={i}>{l.t.toFixed(0).padStart(3)}s {l.msg}</li>)}
            </ul>
          </details>
        ))}
      </section>
    </div>
  );
}

function MobileNav({ view, setView, badge }: { view: View; setView: (v: View) => void; badge: number }) {
  return (
    <nav aria-label="Main" className="glass fixed inset-x-3 bottom-3 z-40 flex gap-1 rounded-[28px] p-1.5 safe-bottom md:hidden" style={{ background: "rgba(30,27,40,0.82)" }}>
      {VIEWS.filter((v) => v.id !== "resources").map((v) => (
        <button key={v.id} onClick={() => setView(v.id)} aria-current={view === v.id ? "page" : undefined}
          className={`relative flex h-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-[22px] text-[11px] font-semibold ${view === v.id ? "bg-white text-ink" : "text-[#D9D3E4]"}`}>
          {v.icon}{v.short}
          {v.id === "now" && badge > 0 && <span className="num absolute right-3 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-ember px-1 text-[10px] font-bold text-[#2A0D09]">{badge}</span>}
        </button>
      ))}
    </nav>
  );
}

function CheckinPanel({ c, alerts, person, onClose, onCall, busy }: {
  c: Checkin; alerts: Alert[]; person?: Resident; onClose: () => void; onCall: () => void; busy: string | null;
}) {
  const cold = c.context?.hazard === "cold";
  const facts: [string, string | undefined][] = cold
    ? [["Heat working", c.heat_working], ["Inside temp", c.indoor_temp], ["Power / gas", c.power_on], ["Indoor heat source", c.unsafe_heating]]
    : [["AC working", c.ac_working], ["Water", c.water], ...(c.playbook === "crew" ? [["Rest break", c.rest_break] as [string, string | undefined]] : [])];
  facts.push(["Symptoms", c.symptoms?.length ? c.symptoms.join(", ") : "none"], ["Rules result", c.risk_level]);
  const myAlerts = alerts.filter((a) => new Date(a.created_at) >= new Date(c.started_at)).slice(0, 3);
  const meta = [person?.city, ...(person?.risk_factors || []), person?.enrolled_by ? `enrolled by ${person.enrolled_by}` : null].filter(Boolean).join(" · ");

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`Call with ${c.resident_name}`}
        className="safe-top h-full w-full max-w-[640px] overflow-y-auto bg-[#1A1723] px-5 pb-10 shadow-2xl sm:px-7"
        onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 z-10 -mx-5 flex items-center gap-3 bg-[#1A1723]/95 px-5 py-3 backdrop-blur sm:-mx-7 sm:px-7">
          <button onClick={onClose} className="inline-flex h-10 items-center gap-1 rounded-full bg-white/[0.08] pl-2 pr-4 text-sm font-semibold hover:bg-white/[0.14]">
            <ChevronLeft size={18} /> Back
          </button>
          {person?.phone && (
            <button onClick={onCall} className="ml-auto inline-flex h-10 items-center gap-1.5 rounded-full bg-white px-4 text-[13px] font-bold text-ink">
              {busy === "call" + c.resident_id ? <Loader2 size={14} className="animate-spin" /> : <Phone size={14} />} Call {c.resident_name?.split(" ")[0]} again
            </button>
          )}
        </div>

        <h2 className="mt-2 font-serif text-[40px] font-normal leading-none tracking-[-0.02em]">{c.resident_name}</h2>
        {meta && <p className="mt-1.5 text-sm text-mist">{meta}</p>}
        <p className="num mt-1 text-xs text-haze">
          {clock(c.started_at)} · {c.purpose === "consent" ? "permission call" : `${cold ? "cold" : "heat"} check-in`} · {c.reason} · attempt {(c.attempt || 0) + 1} · {c.call_status.replace("_", " ")}
        </p>

        {c.case_note && (
          <section className="mt-5 rounded-[22px] bg-white/[0.06] p-4">
            <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-haze"><Sparkles size={12} /> Case note</div>
            <p className="font-serif text-[22px] leading-snug">{c.case_note.summary}</p>
            <p className="mt-1.5 text-sm text-[#E4DEEC]"><b>Why:</b> {c.case_note.reason}</p>
          </section>
        )}

        {c.purpose !== "consent" && (
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {facts.map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-white/[0.06] px-3.5 py-2.5">
                <div className="text-xs text-haze">{k}</div>
                <div className="font-semibold">{v || "—"}</div>
              </div>
            ))}
          </div>
        )}

        {myAlerts.length > 0 && (
          <section className="mt-5">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-haze">Who's been told</h3>
            <ol className="m-0 list-none space-y-2 p-0">
              {myAlerts.map((a) => (
                <li key={a._id} className="flex gap-3 rounded-2xl bg-white/[0.05] px-3.5 py-3 text-sm">
                  <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${a.level === "emergency" ? "bg-ember" : "bg-amber"}`} />
                  <span>
                    <span className="font-semibold">{a.reason}</span>
                    <span className="block text-[13px] text-mist">
                      {clock(a.created_at)} · {a.notified?.length ? `told ${a.notified.join(", ")}` : "no contact reached"}
                      {a.resolved_at ? ` · acknowledged by ${a.acknowledged_by || "staff"}` : " · waiting for staff"}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {!!c.memory_used?.length && (
          <section className="mt-5">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-haze">What Kinwell remembered</h3>
            <ul className="m-0 list-none space-y-1.5 p-0">{c.memory_used.map((m, i) => <li key={i} className="rounded-2xl bg-white/[0.05] px-3.5 py-2.5 text-sm">{m}</li>)}</ul>
          </section>
        )}

        <section className="mt-5">
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-haze"><List size={12} /> Transcript</h3>
          <div className="flex flex-col gap-2">
            {(c.transcript || []).filter((t) => t.text.trim()).map((t, i) => (
              <div key={i} className={`max-w-[85%] px-3.5 py-2.5 text-sm leading-relaxed ${t.role === "USER"
                ? "self-end rounded-[18px_18px_6px_18px] bg-white text-ink" : "self-start rounded-[18px_18px_18px_6px] bg-white/[0.08]"}`}>
                {t.text}
              </div>
            ))}
            {!c.transcript?.length && <p className="text-sm text-haze">No transcript (call not answered or still in progress).</p>}
          </div>
          <p className="mt-4 flex items-center gap-1.5 text-xs text-haze"><Lock size={12} /> Audio is never stored. Transcripts expire after 30 days.</p>
        </section>
      </div>
    </div>
  );
}
