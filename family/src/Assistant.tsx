import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Mic, MicOff } from "lucide-react";
import { api, emptyDraft, type Draft, type Person } from "./api";
import { Spinner } from "./ui";
import Typewriter from "./Typewriter";

type Msg = { role: "user" | "assistant"; text: string; typing?: boolean };

const OPENING: Msg = {
  role: "assistant",
  typing: true,
  text: "Hi! Who would you like HeatCheck to look after? Tell me about them, like \"my dad, Jorge\".",
};

// Browser speech-to-text (Chrome, Edge, Safari). Hidden where unsupported.
type SR = { lang: string; interimResults: boolean; start(): void; stop(): void; onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
const SpeechRec: (new () => SR) | undefined =
  (window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR }).SpeechRecognition ||
  (window as unknown as { webkitSpeechRecognition?: new () => SR }).webkitSpeechRecognition;

function chipsFor(missing: string[]): string[] {
  switch (missing[0]) {
    case "language": return ["English", "Spanish"];
    case "backup": return ["Just me"];
    default: return [];
  }
}

export default function Assistant({ onAdded, compact = false }: { onAdded: (p: Person) => void; compact?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([OPENING]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [missing, setMissing] = useState<string[]>(["name"]);
  const [ready, setReady] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [listening, setListening] = useState(false);
  const recRef = useRef<SR | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, busy, ready]);
  const follow = useCallback(() => endRef.current?.scrollIntoView({ block: "end" }), []);
  const finishTyping = useCallback((i: number) => setMsgs((ms) => ms.map((m, j) => (j === i ? { ...m, typing: false } : m))), []);
  const typing = msgs.some((m) => m.typing);

  async function send(t: string) {
    const clean = t.trim();
    if (!clean || busy) return;
    const next: Msg[] = [...msgs.map((m) => ({ ...m, typing: false })), { role: "user", text: clean }];
    setMsgs(next); setText(""); setBusy(true); setError("");
    try {
      const r = await api.assistant(next.slice(1), draft);
      setDraft(r.draft); setMissing(r.missing); setReady(r.ready);
      setMsgs([...next, { role: "assistant", text: r.reply, typing: true }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    setAdding(true); setError("");
    try {
      const r = await api.add(draft);
      onAdded(r.person);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  function toggleMic() {
    if (!SpeechRec) return;
    if (listening) { recRef.current?.stop(); return; }
    const rec = new SpeechRec();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = false;
    rec.onresult = (e) => {
      const said = Array.from(e.results).map((r) => r[0].transcript).join(" ");
      setText((t) => (t ? t + " " : "") + said);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  }

  const first = draft.name.split(" ")[0] || "them";
  const rows: [string, string][] = [
    ["Name", [draft.name, draft.relationship && `· ${draft.relationship}`].filter(Boolean).join(" ")],
    ["Phone", draft.phone],
    ["Home", draft.address],
    ["Calls in", draft.language === "es" ? "Spanish" : draft.language === "en" ? "English" : ""],
    ["Watch for", draft.address ? "Heat and cold" : ""],
    ["Backup", draft.backup_skipped ? "Just you" : [draft.backup_name, draft.backup_relationship && `(${draft.backup_relationship})`].filter(Boolean).join(" ")],
  ];
  const started = rows.some(([, v]) => v);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={`no-scrollbar flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto ${compact ? "" : "px-4"} pb-2 text-[15px] leading-snug`} aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={`fade-in max-w-[84%] px-3.5 py-2.5 ${m.role === "user" ? "bubble-user self-end" : "bubble-bot self-start"}`}>
            {m.typing ? <Typewriter text={m.text} onTick={follow} onDone={() => finishTyping(i)} /> : m.text}
          </div>
        ))}
        {busy && <div className="bubble-bot self-start px-4 py-3"><Spinner /></div>}

        {started && (
          <div className="glass fade-in mt-1 flex flex-col gap-2 rounded-[24px] px-4 py-3.5 text-[14px]">
            <span className="eyebrow text-[11px]">So far</span>
            {rows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <span className="muted">{k}</span>
                <span className={`text-right ${v ? "font-semibold" : "muted"}`}>{v || "…"}</span>
              </div>
            ))}
          </div>
        )}
        {ready && !typing && (
          <button className="btn-ink fade-in mt-1 h-[52px] text-[16px]" onClick={add} disabled={adding}>
            {adding ? "Adding…" : `Add and ask ${first}`}
          </button>
        )}
        {error && <p className="rounded-2xl bg-[rgba(180,83,42,0.1)] px-4 py-3 text-[14px] text-[#8A3B1C]" role="alert">{error}</p>}
        <div ref={endRef} />
      </div>

      <div className={`flex flex-col gap-2.5 ${compact ? "pt-2" : "px-4 pt-2"}`}>
        {!ready && !typing && chipsFor(missing).length > 0 && (
          <div className="flex flex-wrap gap-2">
            {chipsFor(missing).map((c) => (
              <button key={c} className="glass h-10 rounded-full px-4 text-[14px] font-medium" onClick={() => send(c)}>{c}</button>
            ))}
          </div>
        )}
        <form className="glass flex h-14 items-center gap-1.5 rounded-full pl-5 pr-1.5" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <label htmlFor="chat" className="sr-only">Message</label>
          <input id="chat" value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening…" : "Type or tap the mic…"}
            className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-[var(--muted)]" autoComplete="off" />
          {SpeechRec && (
            <button type="button" onClick={toggleMic} aria-label={listening ? "Stop listening" : "Speak"}
              className={`flex h-11 w-11 items-center justify-center rounded-full ${listening ? "bg-[#D9774D] text-white" : "bg-white/80"}`}>
              {listening ? <MicOff size={20} /> : <Mic size={20} />}
            </button>
          )}
          <button aria-label="Send" className="btn-ink flex h-11 w-11 items-center justify-center" disabled={busy || !text.trim()}><ArrowUp size={18} /></button>
        </form>
      </div>
    </div>
  );
}
