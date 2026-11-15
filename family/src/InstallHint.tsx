import { useEffect, useState } from "react";
import { Share, X } from "lucide-react";

type BIPEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

const KEY = "heatcheck.installHintDismissed";
const standalone = () =>
  matchMedia("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent);

function dismissed() {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}

/** One-time tip on phones: install Kinwell to the home screen so it opens full screen, like an app. */
export default function InstallHint() {
  const [evt, setEvt] = useState<BIPEvent | null>(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (standalone() || dismissed()) return;
    const onPrompt = (e: Event) => { e.preventDefault(); setEvt(e as BIPEvent); setShow(true); };
    addEventListener("beforeinstallprompt", onPrompt);
    if (isIOS()) setShow(true);
    return () => removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  const close = () => { setShow(false); try { localStorage.setItem(KEY, "1"); } catch { /* private mode */ } };
  if (!show) return null;

  return (
    <div className="glass fade-in flex items-center gap-3 rounded-[22px] px-4 py-3 text-[14px]">
      <div className="flex-1 leading-snug">
        {evt ? "Install Kinwell for a full-screen app on your phone." : (
          <>For full screen, tap <Share size={14} className="inline -mt-0.5" /> <strong>Share</strong>, then <strong>Add to Home Screen</strong>.</>
        )}
      </div>
      {evt && (
        <button className="btn-ink h-9 px-4 text-[13px]" onClick={async () => { await evt.prompt(); await evt.userChoice; close(); }}>
          Install
        </button>
      )}
      <button aria-label="Dismiss" onClick={close} className="flex h-9 w-9 items-center justify-center rounded-full"><X size={16} /></button>
    </div>
  );
}
