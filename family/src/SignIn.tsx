import { useState } from "react";
import { Lock } from "lucide-react";
import { confirmSignUp, resendCode, signIn, signUp } from "./auth";
import { Backdrop, Logo } from "./ui";

type Mode = "signin" | "signup" | "confirm";

export default function SignIn({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setNote("");
    try {
      if (mode === "signin") {
        await signIn(email, password);
        onDone();
      } else if (mode === "signup") {
        await signUp(name, email, password);
        setMode("confirm");
        setNote(`We emailed a 6-digit code to ${email}.`);
      } else {
        await confirmSignUp(email, code);
        await signIn(email, password);
        onDone();
      }
    } catch (err) {
      const msg = (err as Error).message;
      if (msg === "UNCONFIRMED") {
        setMode("confirm");
        await resendCode(email).catch(() => {});
        setNote(`Confirm your email first. We sent a new code to ${email}.`);
      } else setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-dvh">
      <Backdrop />
      <div className="relative z-10 mx-auto flex min-h-dvh max-w-[1180px] flex-wrap items-center gap-10 px-5 py-10 lg:flex-nowrap lg:px-10">
        <section className="flex-[1_1_420px]">
          <Logo size={30} />
          <h1 className="serif mt-8 text-[52px] leading-[0.95] tracking-[-0.02em] lg:text-[84px]">
            Know they're okay on the hottest and coldest days.
          </h1>
          <p className="muted mt-5 max-w-[520px] text-[17px] leading-relaxed">
            Add your mom, dad or grandparent. When the weather turns dangerous, Kinwell calls to check on them
            and tells you right away if something's wrong.
          </p>
          <div className="glass mt-8 hidden max-w-[460px] items-start gap-3 rounded-[22px] p-4 lg:flex">
            <Lock size={18} className="mt-0.5 shrink-0" />
            <p className="text-[14px] leading-snug">They agree before we ever call. You see how they're doing, never a recording of their calls.</p>
          </div>
        </section>

        <form onSubmit={submit} className="glass flex w-full flex-[1_1_380px] flex-col gap-4 rounded-[32px] p-6 lg:max-w-[440px] lg:p-8">
          <h2 className="serif text-[32px] leading-none">
            {mode === "signin" ? "Welcome back" : mode === "signup" ? "Create your account" : "Check your email"}
          </h2>
          {note && <p className="text-[14px]" role="status">{note}</p>}

          {mode === "signup" && (
            <label className="flex flex-col gap-1.5 text-[14px] font-medium">Your name
              <input className="field" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
            </label>
          )}
          {mode !== "confirm" && (
            <>
              <label className="flex flex-col gap-1.5 text-[14px] font-medium">Email
                <input className="field" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
              </label>
              <label className="flex flex-col gap-1.5 text-[14px] font-medium">Password
                <input className="field" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength={8} required />
              </label>
            </>
          )}
          {mode === "confirm" && (
            <label className="flex flex-col gap-1.5 text-[14px] font-medium">6-digit code
              <input className="field tracking-[0.3em]" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" required />
            </label>
          )}

          {error && <p className="rounded-2xl bg-[rgba(180,83,42,0.1)] px-4 py-3 text-[14px] text-[#8A3B1C]" role="alert">{error}</p>}

          <button className="btn-ink mt-2 h-[52px] text-[16px]" disabled={busy}>
            {busy ? "One moment…" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Confirm and sign in"}
          </button>

          {mode === "signin" && (
            <button type="button" className="btn-soft h-12 text-[15px]" onClick={() => { setMode("signup"); setError(""); }}>
              New here? Create an account
            </button>
          )}
          {mode === "signup" && (
            <button type="button" className="btn-soft h-12 text-[15px]" onClick={() => { setMode("signin"); setError(""); }}>
              Already have an account? Sign in
            </button>
          )}
          {mode === "confirm" && (
            <button type="button" className="btn-soft h-12 text-[15px]" onClick={() => resendCode(email).then(() => setNote("New code sent.")).catch((e) => setError(e.message))}>
              Send a new code
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
