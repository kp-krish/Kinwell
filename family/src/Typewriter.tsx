import { useEffect, useRef, useState } from "react";

const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Reveals text character by character, pausing briefly at punctuation, like someone typing live. */
export default function Typewriter({ text, onTick, onDone }: { text: string; onTick?: () => void; onDone?: () => void }) {
  const [n, setN] = useState(reduced ? text.length : 0);
  const done = useRef(false);

  useEffect(() => {
    if (n >= text.length) {
      if (!done.current) { done.current = true; onDone?.(); }
      return;
    }
    const ch = text[n - 1] || "";
    const delay = ".!?".includes(ch) ? 220 : ",;:".includes(ch) ? 110 : 14 + Math.random() * 18;
    const t = setTimeout(() => { setN((x) => Math.min(text.length, x + (text.length > 220 ? 2 : 1))); onTick?.(); }, delay);
    return () => clearTimeout(t);
  }, [n, text, onTick, onDone]);

  return (
    <span>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{text.slice(0, n)}{n < text.length && <span className="caret" />}</span>
    </span>
  );
}
