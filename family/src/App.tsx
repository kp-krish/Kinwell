import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, Home as HomeIcon, LogOut, MessageCircle, Plus, Users } from "lucide-react";
import { api, AuthError, type Hazard, type Me } from "./api";
import { idToken, signOut } from "./auth";
import Assistant from "./Assistant";
import { EmptyPeople, Hero, ModeSwitch, PersonCard } from "./Home";
import PersonView from "./PersonView";
import InstallHint from "./InstallHint";
import SignIn from "./SignIn";
import { Backdrop, Logo, Spinner, autoMode } from "./ui";

type Route = { name: "home" } | { name: "add" } | { name: "person"; id: string };

function parse(hash: string): Route {
  const h = hash.replace(/^#\/?/, "");
  if (h === "add") return { name: "add" };
  if (h.startsWith("p/")) return { name: "person", id: h.slice(2) };
  return { name: "home" };
}
const go = (r: Route) => { location.hash = r.name === "home" ? "/" : r.name === "add" ? "/add" : `/p/${r.id}`; };

function useWide() {
  const q = "(min-width: 1024px)";
  const [wide, setWide] = useState(() => matchMedia(q).matches);
  useEffect(() => {
    const m = matchMedia(q);
    const f = () => setWide(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return wide;
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [route, setRoute] = useState<Route>(parse(location.hash));
  const [mode, setModeState] = useState<Hazard | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const wide = useWide();

  useEffect(() => { idToken().then((t) => setAuthed(!!t)); }, []);
  useEffect(() => {
    const f = () => setRoute(parse(location.hash));
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);

  const load = useCallback(async () => {
    try { setMe(await api.me()); }
    catch (e) { if (e instanceof AuthError) { setAuthed(false); setMe(null); } }
  }, []);

  useEffect(() => {
    if (!authed) return;
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [authed, load]);

  const activeMode: Hazard = mode || (me ? autoMode(me.people) : "heat");
  useEffect(() => {
    document.documentElement.dataset.mode = activeMode;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", activeMode === "cold" ? "#ECF0F5" : "#F3EEF0");
  }, [activeMode]);

  if (authed === null) return <div className="flex min-h-dvh items-center justify-center"><Spinner /></div>;
  if (!authed) return <SignIn onDone={() => { setAuthed(true); go({ name: "home" }); }} />;
  if (!me) return <div className="relative flex min-h-dvh items-center justify-center"><Backdrop /><Spinner className="relative" /></div>;

  const doSignOut = () => { if (confirm("Sign out of Kinwell?")) { signOut(); setAuthed(false); setMe(null); } };
  const onAdded = (id: string) => { load(); setRefreshKey((k) => k + 1); go({ name: "person", id }); };
  const setMode = (m: Hazard) => setModeState(m);

  return wide
    ? <Desktop me={me} route={route} mode={activeMode} setMode={setMode} onAdded={onAdded} signOut={doSignOut} refreshKey={refreshKey} reload={load} />
    : <Phone me={me} route={route} mode={activeMode} setMode={setMode} onAdded={onAdded} signOut={doSignOut} refreshKey={refreshKey} reload={load} />;
}

type LayoutProps = {
  me: Me; route: Route; mode: Hazard; setMode: (m: Hazard) => void; onAdded: (id: string) => void;
  signOut: () => void; refreshKey: number; reload: () => void;
};

function Phone({ me, route, mode, setMode, onAdded, signOut, refreshKey, reload }: LayoutProps) {
  const back = (
    <button onClick={() => go({ name: "home" })} aria-label="Back" className="-ml-2 flex h-11 w-11 items-center justify-center rounded-full">
      <ChevronLeft size={24} />
    </button>
  );
  return (
    <div className="relative min-h-dvh">
      <Backdrop />
      <div className="relative z-10 mx-auto flex min-h-dvh max-w-[520px] flex-col">
        {route.name === "home" && (
          <>
            <header className="safe-top flex items-center justify-between px-5">
              <Logo />
              <ModeSwitch mode={mode} setMode={setMode} />
            </header>
            <div className="px-5 pt-6"><Hero me={me} mode={mode} /></div>
            <div className="px-5 pt-6"><InstallHint /></div>
            <h1 className="eyebrow px-5 pb-3 pt-6">Your people</h1>
            <div className="flex flex-col gap-3 px-5 pb-32">
              {me.people.length === 0 && <EmptyPeople onAdd={() => go({ name: "add" })} />}
              {me.people.map((p) => <PersonCard key={p.id} p={p} onOpen={() => go({ name: "person", id: p.id })} />)}
            </div>
            <nav className="glass safe-bottom fixed left-1/2 flex h-[68px] w-[calc(100%-40px)] max-w-[480px] -translate-x-1/2 items-center justify-between rounded-full pl-3.5 pr-2.5">
              <div className="flex gap-1">
                <button aria-label="Home" className="flex h-12 w-12 items-center justify-center rounded-full bg-white"><HomeIcon size={22} /></button>
                <button aria-label="Assistant" onClick={() => go({ name: "add" })} className="flex h-12 w-12 items-center justify-center rounded-full"><MessageCircle size={22} /></button>
                <button aria-label="Sign out" onClick={signOut} className="flex h-12 w-12 items-center justify-center rounded-full"><LogOut size={21} /></button>
              </div>
              <button onClick={() => go({ name: "add" })} className="btn-ink flex h-[50px] items-center gap-2 px-5 text-[15px]"><Plus size={18} />Add</button>
            </nav>
          </>
        )}
        {route.name === "add" && (
          <div className="safe-pb flex h-dvh flex-col">
            <header className="safe-top flex items-center gap-1 px-4 pb-3">
              {back}
              <div className="flex flex-col">
                <span className="serif text-[24px] leading-none">Add someone</span>
                <span className="muted text-[12px]">Type or talk. Takes about a minute.</span>
              </div>
            </header>
            <div className="min-h-0 flex-1"><Assistant onAdded={(p) => onAdded(p.id)} /></div>
          </div>
        )}
        {route.name === "person" && (
          <div className="safe-top px-5 pb-10">
            <header className="pb-2">{back}</header>
            <PersonView id={route.id} refreshKey={refreshKey} onRemoved={() => { reload(); go({ name: "home" }); }} />
          </div>
        )}
      </div>
    </div>
  );
}

function Desktop({ me, route, mode, setMode, onAdded, signOut, refreshKey, reload }: LayoutProps) {
  const selected = route.name === "person" ? route.id : route.name === "home" && me.people.length ? me.people[0].id : null;
  const showAssistant = route.name === "add" || (!selected && route.name === "home");
  const places = Array.from(new Set(me.people.filter((p) => p.city).map((p) => p.city)));
  return (
    <div className="relative min-h-dvh">
      <Backdrop />
      <div className="relative z-10 mx-auto flex min-h-dvh max-w-[1440px] gap-6 p-7">
        <aside className="glass sticky top-7 flex h-[calc(100dvh-56px)] w-[224px] shrink-0 flex-col gap-1 rounded-[32px] px-3.5 py-6">
          <span className="px-3 pb-6"><Logo size={30} /></span>
          <button onClick={() => go({ name: "home" })}
            className={`flex h-12 items-center gap-3 rounded-2xl px-3.5 text-[15px] ${route.name !== "add" ? "bg-white font-semibold" : "font-medium"}`}>
            <Users size={18} />People
          </button>
          <button onClick={() => go({ name: "add" })}
            className={`flex h-12 items-center gap-3 rounded-2xl px-3.5 text-[15px] ${route.name === "add" ? "bg-white font-semibold" : "font-medium"}`}>
            <MessageCircle size={18} />Assistant
          </button>
          {places.length > 0 && (
            <div className="mt-auto flex flex-col gap-1 rounded-[20px] bg-white/55 p-3.5">
              <span className="eyebrow text-[11px]">Watching</span>
              <span className="text-[14px] leading-snug">Heat and cold in {places.join(", ")}</span>
            </div>
          )}
          <button onClick={signOut} className={`${places.length ? "mt-2" : "mt-auto"} flex h-11 items-center gap-3 rounded-2xl px-3.5 text-[14px] font-medium`}>
            <LogOut size={17} />Sign out
          </button>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col gap-7 py-3">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <Hero me={me} mode={mode} large />
            <ModeSwitch mode={mode} setMode={setMode} large />
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-4">
            {me.people.length === 0 && <EmptyPeople onAdd={() => go({ name: "add" })} />}
            {me.people.map((p) => (
              <PersonCard key={p.id} p={p} selected={!showAssistant && p.id === selected} onOpen={() => go({ name: "person", id: p.id })} />
            ))}
            {me.people.length > 0 && (
              <button onClick={() => go({ name: "add" })}
                className="flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-[28px] border-[1.5px] border-dashed border-[var(--muted)]/50 bg-white/10 text-[15px] font-medium">
                <Plus size={22} />Add someone
              </button>
            )}
          </div>
        </main>

        <section className="glass sticky top-7 flex h-[calc(100dvh-56px)] w-[400px] shrink-0 flex-col rounded-[32px] p-6">
          {showAssistant ? (
            <>
              <div className="flex items-baseline justify-between pb-3">
                <h2 className="serif text-[30px] leading-none">Assistant</h2>
                <span className="muted text-[13px]">Add someone</span>
              </div>
              <div className="min-h-0 flex-1"><Assistant compact onAdded={(p) => onAdded(p.id)} /></div>
            </>
          ) : selected ? (
            <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
              <PersonView id={selected} refreshKey={refreshKey} onRemoved={() => { reload(); go({ name: "home" }); }} />
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
