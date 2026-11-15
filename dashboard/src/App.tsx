import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, BellRing, CheckCircle2, ClipboardList, Globe2, HardHat, Loader2, Phone, PhoneCall,
  RefreshCw, Snowflake, Sparkles, ThermometerSun, X,
} from "lucide-react";
import { api, ago, clock, type Briefing, type Checkin, type Resident, type State } from "./api";
import MapView from "./MapView";
import { STATUS_META, latestByResident, statusOf, type Status } from "./status";

type Tab = "residents" | "crews";

export default function App() {
  const [state, setState] = useState<State | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("residents");
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
  const residents = state?.residents || [];
  const counts = useMemo(() => {
    const c: Record<Status, number> = { emergency: 0, warning: 0, no_answer: 0, calling: 0, safe: 0, pending: 0 };
    residents.forEach((r) => c[statusOf(r, latest.get(r._id))]++);
    return c;
  }, [residents, latest]);
  const openAlerts = (state?.alerts || []).filter((a) => !a.resolved_at);
  const liveCenters = (state?.resources || []).filter((r) => r.source_url && r.source_url !== "seed");
  const lastFetch = liveCenters.map((r) => r.fetched_at || "").sort().pop();

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

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex flex-wrap items-center gap-3 border-b border-stone-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-heat-500 text-white shadow-sm"><ThermometerSun size={20} /></div>
          <div>
            <h1 className="text-lg font-semibold leading-tight">Kinwell</h1>
            <p className="text-xs text-stone-500">Heat and cold check-ins</p>
          </div>
        </div>
        <div className="ml-0 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-1.5 text-sm text-red-800 ring-1 ring-red-200 sm:ml-4">
          <AlertTriangle size={16} /> <span className="font-medium">NWS Extreme Heat Warning</span> <span className="text-red-600">· high 112°F</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => run("simulate", api.simulate)}
            disabled={!!busy}
            className="inline-flex items-center gap-2 rounded-lg bg-heat-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-heat-700 disabled:opacity-60">
            {busy === "simulate" ? <Loader2 size={16} className="animate-spin" /> : <BellRing size={16} />}
            Simulate heat warning
          </button>
          <button
            onClick={() => run("simulateCold", api.simulateCold)}
            disabled={!!busy}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-sky-800 disabled:opacity-60">
            {busy === "simulateCold" ? <Loader2 size={16} className="animate-spin" /> : <Snowflake size={16} />}
            Simulate cold warning
          </button>
        </div>
      </header>

      {err && <div className="bg-red-600 px-4 py-1.5 text-sm text-white">Connection problem: {err.slice(0, 160)}</div>}

      {/* Stat strip */}
      <div className="grid grid-cols-3 gap-2 border-b border-stone-200 bg-white px-4 py-2 sm:grid-cols-6 sm:px-6">
        {(["emergency", "warning", "no_answer", "calling", "safe", "pending"] as Status[]).map((s) => (
          <div key={s} className="flex items-center gap-2 rounded-lg px-2 py-1">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_META[s].color }} />
            <span className="text-xl font-semibold tabular-nums">{counts[s]}</span>
            <span className="text-xs text-stone-500">{STATUS_META[s].label}</span>
          </div>
        ))}
      </div>

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[1fr_420px]">
        {/* Map */}
        <section className="relative min-h-[320px] overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-stone-200">
          <MapView residents={residents} latest={latest} resources={state?.resources || []} onSelect={onSelectResident} />
          <div className="pointer-events-none absolute bottom-3 left-3 rounded-lg bg-white/95 px-3 py-2 text-xs shadow ring-1 ring-stone-200">
            <div className="mb-1 font-medium">Legend</div>
            <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-green-600" /> person (circle) · crew worker (square)</div>
            <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-blue-600" /> open cooling spot, live hours</div>
          </div>
        </section>

        {/* Side panel */}
        <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto">
          {/* Alerts */}
          <Card title="Open alerts" icon={<BellRing size={16} />} badge={openAlerts.length || undefined}>
            {openAlerts.length === 0 && <Empty>No open alerts.</Empty>}
            {openAlerts.map((a) => (
              <div key={a._id} className={`rounded-lg p-3 ring-1 ${a.level === "emergency" ? "bg-red-50 ring-red-200" : "bg-amber-50 ring-amber-200"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">{a.resident_name}{a.playbook === "crew" && <span className="ml-1 text-xs font-normal text-stone-500">(crew)</span>}</div>
                    <div className="text-sm text-stone-700">{a.reason}</div>
                    <div className="mt-1 text-xs text-stone-500">
                      {a.notified?.length ? <>Alerted {a.notified.join(", ")}</> : "No contact reached"} · {ago(a.created_at, now)}
                    </div>
                  </div>
                  <button onClick={() => run("ack" + a._id, () => api.ack(a._id))}
                    className="shrink-0 rounded-md bg-white px-2 py-1 text-xs font-medium ring-1 ring-stone-300 hover:bg-stone-50">
                    Acknowledge
                  </button>
                </div>
              </div>
            ))}
          </Card>

          {/* Briefing */}
          <Card title="Who needs a human call" icon={<Sparkles size={16} />}
            action={<button onClick={loadBriefing} className="inline-flex items-center gap-1 text-xs font-medium text-heat-700 hover:underline">
              {briefingBusy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} {briefing ? "Refresh" : "Generate"}
            </button>}>
            {!briefing && <Empty>Gemini ranks today's check-ins so staff call the right people first.</Empty>}
            {briefing && (
              <div>
                <p className="mb-2 text-sm font-medium">{briefing.headline}</p>
                <ol className="space-y-1.5">
                  {briefing.items.sort((a, b) => a.priority - b.priority).map((i) => (
                    <li key={i.resident_id} className="flex gap-2 text-sm">
                      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-heat-100 text-xs font-semibold text-heat-700">{i.priority}</span>
                      <span><b>{i.name}</b>: {i.reason}</span>
                    </li>
                  ))}
                </ol>
                {briefing.model && <p className="mt-2 text-[11px] text-stone-400">Generated by {briefing.model}</p>}
              </div>
            )}
          </Card>

          {/* Tabs: residents / crews */}
          <Card title="Check-ins" icon={<ClipboardList size={16} />}
            action={<div className="flex rounded-md bg-stone-100 p-0.5 text-xs">
              {(["residents", "crews"] as Tab[]).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`rounded px-2 py-1 capitalize ${tab === t ? "bg-white shadow-sm font-medium" : "text-stone-500"}`}>
                  {t === "crews" ? "Crew Check" : "Residents"}
                </button>
              ))}
            </div>}>
            {tab === "residents" ? (
              <PeopleList people={residents.filter((r) => r.playbook === "resident")} latest={latest} now={now}
                onOpen={openCheckin} onCall={(id) => run("call" + id, () => api.call(id))} busy={busy} />
            ) : (
              <CrewView state={state} latest={latest} now={now} onOpen={openCheckin}
                onCall={(id) => run("call" + id, () => api.call(id))} busy={busy}
                onStartShift={(cid) => run("shift" + cid, () => api.startShift(cid))} />
            )}
          </Card>

          {/* Resource Scout */}
          <Card title="Resource Scout" icon={<Globe2 size={16} />}
            action={<button onClick={() => run("scout", api.refreshScout)} className="inline-flex items-center gap-1 text-xs font-medium text-heat-700 hover:underline">
              {busy === "scout" ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Refresh resources
            </button>}>
            <p className="text-sm text-stone-600">
              {liveCenters.length} cooling spots with today's hours · fetched {clock(lastFetch)} ({ago(lastFetch, now)})
            </p>
            <p className="mb-2 text-[11px] text-stone-400">TinyFish web agent on Maritime → Atlas. The voice agent quotes only these records.</p>
            {(state?.scout_runs || []).slice(0, 2).map((r) => (
              <details key={r._id} className="mb-1 rounded-md bg-stone-50 px-2 py-1.5 text-xs ring-1 ring-stone-200">
                <summary className="cursor-pointer">
                  <span className={r.status === "ok" ? "text-green-700" : r.status === "running" ? "text-blue-700" : "text-red-700"}>●</span>{" "}
                  {r.source} · {r.status}{r.sites_saved != null ? ` · ${r.sites_saved} saved` : ""} · {clock(r.started_at)}
                </summary>
                <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-stone-600">
                  {r.log.map((l, i) => <li key={i}>{l.t.toFixed(0).padStart(3)}s {l.msg}</li>)}
                </ul>
              </details>
            ))}
          </Card>
        </aside>
      </main>

      {selected && <CheckinDrawer c={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Card({ title, icon, badge, action, children }: { title: string; icon: React.ReactNode; badge?: number; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-stone-200">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-stone-500">{icon}</span>
        <h2 className="text-sm font-semibold">{title}</h2>
        {badge != null && <span className="rounded-full bg-red-600 px-1.5 text-xs font-semibold text-white">{badge}</span>}
        <div className="ml-auto">{action}</div>
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-stone-500">{children}</p>;
}

function Chip({ s }: { s: Status }) {
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${STATUS_META[s].chip}`}>{STATUS_META[s].label}</span>;
}

function PeopleList({ people, latest, now, onOpen, onCall, busy }: {
  people: Resident[]; latest: Map<string, Checkin>; now: number; onOpen: (id: string) => void; onCall: (id: string) => void; busy: string | null;
}) {
  const order: Status[] = ["emergency", "warning", "no_answer", "calling", "pending", "safe"];
  const sorted = [...people].sort((a, b) => order.indexOf(statusOf(a, latest.get(a._id))) - order.indexOf(statusOf(b, latest.get(b._id))));
  return (
    <ul className="divide-y divide-stone-100">
      {sorted.map((r) => {
        const c = latest.get(r._id);
        const st = statusOf(r, c);
        return (
          <li key={r._id} className="flex items-center gap-2 py-2">
            <button onClick={() => c && onOpen(c._id)} className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium">{r.name}</span>
                <Chip s={st} />
              </div>
              <div className="truncate text-xs text-stone-500">
                {c ? <>{c.case_note?.summary || (c.risk_reasons?.join(", ") || c.call_status)} · {ago(c.started_at, now)}</> : r.risk_factors?.join(", ")}
              </div>
            </button>
            {r.phone && (
              <button title="Call now" onClick={() => onCall(r._id)} className="rounded-md p-1.5 text-stone-500 ring-1 ring-stone-200 hover:bg-stone-50">
                {busy === "call" + r._id ? <Loader2 size={14} className="animate-spin" /> : <Phone size={14} />}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function CrewView({ state, latest, now, onOpen, onCall, busy, onStartShift }: {
  state: State | null; latest: Map<string, Checkin>; now: number; onOpen: (id: string) => void; onCall: (id: string) => void; busy: string | null;
  onStartShift: (crewId: string) => void;
}) {
  const crews = state?.crews || [];
  return (
    <div className="space-y-3">
      {crews.map((crew) => {
        const workers = (state?.residents || []).filter((r) => r.crew_id === crew._id);
        const log = (state?.checkins || []).filter((c) => workers.some((w) => w._id === c.resident_id)).slice(0, 8);
        return (
          <div key={crew._id}>
            <div className="mb-1 flex items-center gap-2 text-sm">
              <HardHat size={14} className="text-heat-600" /><b>{crew.employer}</b> · {crew.name}
              <span className="ml-auto text-xs text-stone-500">Shift {crew.shift_start}–{crew.shift_end}, every {crew.interval_min / 60} h</span>
            </div>
            <button onClick={() => onStartShift(crew._id)}
              className="mb-1 inline-flex items-center gap-1.5 rounded-md bg-stone-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-stone-700">
              {busy === "shift" + crew._id ? <Loader2 size={12} className="animate-spin" /> : <PhoneCall size={12} />} Start shift check-ins
            </button>
            <PeopleList people={workers} latest={latest} now={now} onOpen={onOpen} onCall={onCall} busy={busy} />
            <div className="mt-1 text-xs font-medium text-stone-500">Shift log</div>
            <ul className="text-xs text-stone-600">
              {log.length === 0 && <li className="text-stone-400">No check-ins this shift yet.</li>}
              {log.map((c) => (
                <li key={c._id} className="flex gap-2 py-0.5">
                  <span className="w-16 tabular-nums text-stone-400">{clock(c.started_at)}</span>
                  <span className="truncate">{c.resident_name}: {c.call_status === "no_answer" ? "missed check-in" :
                    c.risk_level === "clear" ? "checked in" : (c.risk_reasons?.join(", ") || c.call_status)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-stone-400">Privacy: supervisors see answers only when a red flag or missed check-in fires.</p>
          </div>
        );
      })}
    </div>
  );
}

function CheckinDrawer({ c, onClose }: { c: Checkin; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-lg overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold">{c.resident_name}</h3>
            <p className="text-xs text-stone-500">{clock(c.started_at)} · {c.reason} · attempt {(c.attempt || 0) + 1} · {c.call_status}</p>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-stone-100"><X size={18} /></button>
        </div>

        {c.case_note && (
          <div className="mb-4 rounded-lg bg-heat-50 p-3 ring-1 ring-heat-100">
            <div className="mb-1 flex items-center gap-1 text-xs font-medium text-heat-700"><Sparkles size={12} /> Gemini case note</div>
            <p className="text-sm">{c.case_note.summary}</p>
            <p className="mt-1 text-xs text-stone-600"><b>Why:</b> {c.case_note.reason}</p>
          </div>
        )}

        <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
          <Fact k="Rules result" v={c.risk_level || "—"} />
          <Fact k="AC working" v={c.ac_working || "—"} />
          <Fact k="Water" v={c.water || "—"} />
          <Fact k="Symptoms" v={c.symptoms?.length ? c.symptoms.join(", ") : "none"} />
        </div>

        {!!c.memory_used?.length && (
          <div className="mb-4">
            <div className="mb-1 text-xs font-medium text-stone-500">Memory used on this call (Supermemory)</div>
            <ul className="list-disc pl-5 text-sm text-stone-700">{c.memory_used.map((m, i) => <li key={i}>{m}</li>)}</ul>
          </div>
        )}

        <div className="mb-1 flex items-center gap-1 text-xs font-medium text-stone-500"><PhoneCall size={12} /> Transcript</div>
        <div className="space-y-2">
          {(c.transcript || []).filter((t) => t.text.trim()).map((t, i) => (
            <div key={i} className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${t.role === "USER" ? "ml-auto bg-blue-50 text-blue-950" : "bg-stone-100"}`}>
              {t.text}
            </div>
          ))}
          {!c.transcript?.length && <Empty>No transcript (call not answered or still in progress).</Empty>}
        </div>
        <p className="mt-4 flex items-center gap-1 text-[11px] text-stone-400"><CheckCircle2 size={12} /> Audio is never stored. Transcripts expire automatically after 30 days.</p>
      </div>
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md bg-stone-50 px-2 py-1.5 ring-1 ring-stone-200">
      <div className="text-[11px] text-stone-500">{k}</div>
      <div className="font-medium">{v}</div>
    </div>
  );
}
