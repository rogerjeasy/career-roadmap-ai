"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";

// ─── Logo mark (light — for dark bg) ─────────────────────────────────────────
function LogoMark() {
  return (
    <svg viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg"
      className="h-8 w-8 shrink-0" aria-hidden="true">
      <path d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
        stroke="#F7F2E8" strokeWidth="1.6" strokeLinecap="round"/>
      <circle cx="3"  cy="22" r="2.2" fill="#C95A3D"/>
      <circle cx="14" cy="6"  r="2.2" fill="#DCE7DC"/>
      <circle cx="25" cy="22" r="2.2" fill="#F7F2E8"/>
    </svg>
  );
}

// ─── Eye icons ────────────────────────────────────────────────────────────────
function EyeOpen() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}
function EyeClosed() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="1" y1="1" x2="23" y2="23"/>
      <path d="M10.94 6.08A6.93 6.93 0 0 1 12 6c7 0 11 6 11 6a16.5 16.5 0 0 1-2.67 3.11M6.53 6.53A13.22 13.22 0 0 0 1 12s4 8 11 8a11.08 11.08 0 0 0 5.47-1.53"/>
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>
    </svg>
  );
}

// ─── Google icon ──────────────────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M17.64 9.2045c0-.638-.0573-1.252-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087C16.6582 14.252 17.64 11.9455 17.64 9.2045z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8055.54-1.8368.859-3.0477.859-2.344 0-4.3282-1.5836-5.036-3.7104H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z" fill="#34A853"/>
      <path d="M3.964 10.71c-.18-.54-.2827-1.1168-.2827-1.71s.1027-1.17.2827-1.71V4.9582H.9573C.3477 6.1732 0 7.5477 0 9s.3477 2.8268.9573 4.0418L3.964 10.71z" fill="#FBBC05"/>
      <path d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5813C13.4627.8918 11.4255 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.964 7.29C4.6718 5.1632 6.656 3.5795 9 3.5795z" fill="#EA4335"/>
    </svg>
  );
}

// ─── GitHub icon ──────────────────────────────────────────────────────────────
function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
  );
}

// ─── Star (gold polygon) ──────────────────────────────────────────────────────
function Star() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-3 shrink-0"
      style={{
        background: "#B68A2E",
        clipPath: "polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)",
      }}
    />
  );
}

// ─── Social proof data ────────────────────────────────────────────────────────
const PROOF = [
  {
    text:   "I went from junior dev to senior in 14 months. The roadmap was eerily accurate.",
    initials: "SK",
    name:   "Sofia K.",
    role:   "Software Engineer · Berlin",
    avatarBg: "#C95A3D",
  },
  {
    text:   "Finally a tool that gave me a concrete plan, not just generic advice.",
    initials: "AM",
    name:   "Alex M.",
    role:   "Product Manager · London",
    avatarBg: "#134E3A",
  },
];

// ─── Password strength logic ──────────────────────────────────────────────────
type Strength = "" | "weak" | "fair" | "strong";

function getStrength(val: string): { score: number; level: Strength; label: string } {
  if (!val) return { score: 0, level: "", label: "" };
  let score = 0;
  if (val.length >= 8)          score++;
  if (/[A-Z]/.test(val))        score++;
  if (/[0-9]/.test(val))        score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;
  if (score <= 1) return { score, level: "weak",   label: "Weak — add uppercase & numbers" };
  if (score <= 3) return { score, level: "fair",   label: "Fair — add a symbol to strengthen" };
  return             { score, level: "strong", label: "Strong password" };
}

const STRENGTH_COLORS: Record<Strength, string> = {
  "":       "#E0D7C2",
  weak:     "#C95A3D",
  fair:     "#B68A2E",
  strong:   "#134E3A",
};

// ─── Reusable input field ─────────────────────────────────────────────────────
interface FieldProps {
  id:           string;
  label:        string;
  type?:        string;
  placeholder:  string;
  autoComplete?: string;
  value:        string;
  onChange:     (v: string) => void;
  rightSlot?:   React.ReactNode;
  hint?:        React.ReactNode;
}
function Field({ id, label, type = "text", placeholder, autoComplete, value, onChange, rightSlot, hint }: FieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-[7px] block text-[12.5px] font-medium tracking-[0.02em] text-ink-2">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          placeholder={placeholder}
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="su-input w-full rounded-[10px] border border-rule-strong bg-paper text-[14px] text-ink placeholder:text-ink-3"
          style={{ height: 46, paddingLeft: 14, paddingRight: rightSlot ? 44 : 14 }}
        />
        {rightSlot && (
          <div className="absolute right-[14px] top-1/2 -translate-y-1/2">{rightSlot}</div>
        )}
      </div>
      {hint}
    </div>
  );
}

// ─── Page component ───────────────────────────────────────────────────────────
export default function RegisterPage() {
  const [firstName,   setFirstName]   = useState("");
  const [lastName,    setLastName]    = useState("");
  const [email,       setEmail]       = useState("");
  const [password,    setPassword]    = useState("");
  const [confirm,     setConfirm]     = useState("");
  const [showPw,      setShowPw]      = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [terms,       setTerms]       = useState(false);
  const [isLoading,   setIsLoading]   = useState(false);

  const { registerWithEmail, loginWithGoogle } = useAuth();

  const strength = getStrength(password);

  const matchState: "" | "ok" | "no" = !confirm ? "" : password === confirm ? "ok" : "no";
  const matchLabel =
    matchState === "ok" ? "✓ Passwords match" :
    matchState === "no" ? "✗ Passwords do not match" : "";

  const handleSubmit = useCallback(async () => {
    if (!terms || matchState !== "ok" || !email || !password) return;
    const displayName = `${firstName} ${lastName}`.trim() || undefined;
    setIsLoading(true);
    try {
      await registerWithEmail(email, password, displayName);
    } finally {
      setIsLoading(false);
    }
  }, [terms, matchState, email, password, firstName, lastName, registerWithEmail]);

  const handleGoogle = useCallback(async () => {
    setIsLoading(true);
    try {
      await loginWithGoogle();
    } finally {
      setIsLoading(false);
    }
  }, [loginWithGoogle]);

  return (
    <>
      <style>{`
        /* Noise grain */
        .grain::before {
          content: ""; position: fixed; inset: 0; z-index: 9999;
          pointer-events: none; opacity: .032;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
          background-size: 128px 128px;
        }

        /* Left ambient gradients */
        .su-left-bg::before {
          content: ""; position: absolute; inset: 0;
          background:
            radial-gradient(ellipse 80% 70% at 30% 60%, #1e3d2f 0%, transparent 70%),
            radial-gradient(ellipse 60% 50% at 70% 20%, #3a1a0e 0%, transparent 60%);
          opacity: 0.7; pointer-events: none;
        }
        .su-left-bg::after {
          content: ""; position: absolute;
          width: 520px; height: 520px;
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 50%;
          bottom: -180px; right: -180px;
          pointer-events: none;
        }

        /* Animations */
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .anim-form   { animation: fadeUp .6s cubic-bezier(.2,.7,.2,1) both; }
        .anim-left-t { animation: fadeUp .7s cubic-bezier(.2,.7,.2,1) .1s both; }
        .anim-left-b { animation: fadeUp .7s cubic-bezier(.2,.7,.2,1) .25s both; }

        /* Input */
        .su-input { outline: none; transition: border-color .15s, box-shadow .15s; }
        .su-input:hover:not(:focus) { border-color: #8A8170; }
        .su-input:focus {
          border-color: #134E3A !important;
          box-shadow: 0 0 0 3px rgba(19,78,58,0.1);
        }

        /* OAuth */
        .su-oauth {
          transition: background .15s, border-color .15s, transform .12s;
        }
        .su-oauth:hover { background: #EFE8D7; border-color: #8A8170; transform: translateY(-1px); }
        .su-oauth:active { transform: translateY(0); }

        /* Primary button */
        .su-btn-primary {
          transition: background .2s ease, transform .12s ease;
          position: relative; overflow: hidden;
        }
        .su-btn-primary::after {
          content: ""; position: absolute; inset: 0;
          background: linear-gradient(135deg, rgba(255,255,255,0.06) 0%, transparent 60%);
          pointer-events: none;
        }
        .su-btn-primary:hover { background: #0E3A2B !important; transform: translateY(-1px); }
        .su-btn-primary:active { transform: translateY(0); }

        /* Strength bar transition */
        .su-bar { height: 3px; flex: 1; border-radius: 99px; transition: background .3s ease; }

        /* pw toggle */
        .su-pw-toggle { transition: color .15s; }
        .su-pw-toggle:hover { color: #15140F; }

        /* Responsive */
        @media (max-width: 800px) {
          .su-shell { grid-template-columns: 1fr !important; }
          .su-left  { display: none !important; }
          .su-right { padding: 48px 24px !important; }
        }
      `}</style>

      <div
        className="grain su-shell"
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: "100vh" }}
      >
        {/* ══════ LEFT PANEL ══════ */}
        <div
          className="su-left su-left-bg relative overflow-hidden"
          style={{
            background: "#15140F",
            display: "flex", flexDirection: "column",
            justifyContent: "space-between",
            padding: "48px 56px",
          }}
        >
          {/* Rings */}
          <div aria-hidden="true" className="pointer-events-none absolute rounded-full"
            style={{ width: 360, height: 360, border: "1px solid rgba(255,255,255,0.05)", bottom: -90, right: -90 }} />
          <div aria-hidden="true" className="pointer-events-none absolute rounded-full"
            style={{ width: 200, height: 200, border: "1px solid rgba(255,255,255,0.07)", bottom: -20, right: -20 }} />

          {/* Logo */}
          <div className="anim-left-t relative z-10">
            <Link href="/"
              className="inline-flex items-center gap-2.5 font-serif text-[20px] font-semibold tracking-[-0.01em] text-bg no-underline"
              aria-label="Career Roadmap AI — home">
              <LogoMark />
              Career Roadmap AI
            </Link>
          </div>

          {/* Tagline + social proof */}
          <div className="anim-left-b relative z-10">

            {/* Users badge */}
            <div
              className="mb-7 inline-flex items-center gap-2 rounded-full px-[14px] py-[7px] text-[12.5px]"
              style={{
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "rgba(247,242,232,0.6)",
              }}
            >
              <span
                className="h-[7px] w-[7px] shrink-0 rounded-full"
                style={{ background: "#4ade80", boxShadow: "0 0 6px #4ade8066" }}
                aria-hidden="true"
              />
              12,400+ professionals already mapped
            </div>

            {/* Quote */}
            <p
              className="mb-6 font-serif font-[300] leading-[1.12] tracking-[-0.025em] text-bg"
              style={{ fontSize: "clamp(32px, 3.6vw, 48px)" }}
            >
              Start your<br />journey{" "}
              <em className="italic" style={{ color: "#F4DDD2" }}>today.</em>
            </p>

            {/* Sub */}
            <p
              className="mb-9 text-[14px] leading-[1.6]"
              style={{ color: "rgba(247,242,232,0.52)", maxWidth: 340 }}
            >
              Set up your account in under two minutes and get a personalised
              career map powered by AI.
            </p>

            {/* Social proof cards */}
            <div className="flex flex-col gap-4">
              {PROOF.map(({ text, initials, name, role, avatarBg }) => (
                <div
                  key={name}
                  className="rounded-[12px] px-5 py-[18px]"
                  style={{
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.09)",
                  }}
                >
                  {/* Stars */}
                  <div className="mb-2.5 flex gap-[3px]" aria-label="5 stars">
                    {Array.from({ length: 5 }).map((_, i) => <Star key={i} />)}
                  </div>
                  {/* Quote */}
                  <p className="mb-3 text-[13px] italic leading-[1.55]"
                    style={{ color: "rgba(247,242,232,0.7)" }}>
                    {text}
                  </p>
                  {/* Author */}
                  <div className="flex items-center gap-2.5">
                    <div
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
                      style={{ background: avatarBg }}
                      aria-hidden="true"
                    >
                      {initials}
                    </div>
                    <div>
                      <div className="text-[12px] font-medium"
                        style={{ color: "rgba(247,242,232,0.85)" }}>{name}</div>
                      <div className="mt-px text-[11px]"
                        style={{ color: "rgba(247,242,232,0.42)" }}>{role}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ══════ RIGHT PANEL ══════ */}
        <div
          className="su-right flex flex-col items-center justify-center overflow-y-auto bg-bg"
          style={{ padding: "48px" }}
        >
          <div className="anim-form w-full" style={{ maxWidth: 400 }}>

            {/* Header */}
            <div className="mb-7">
              <h1 className="mb-2 font-serif font-[400] leading-[1.1] tracking-[-0.025em] text-ink"
                style={{ fontSize: 34 }}>
                Create your<br />
                <em className="italic text-terra">account</em>
              </h1>
              <p className="text-[14px] leading-[1.5] text-ink-3">
                Already have one?{" "}
                <Link href="/login"
                  className="border-b border-green-soft font-medium text-green transition-[border-color] duration-150 hover:border-green">
                  Sign in instead
                </Link>
              </p>
            </div>

            {/* OAuth — side by side */}
            <div className="mb-[22px] flex gap-2.5">
              <button type="button"
                className="su-oauth flex h-11 flex-1 cursor-pointer items-center justify-center gap-2 rounded-[10px] border border-rule-strong bg-paper text-[13.5px] font-medium text-ink disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleGoogle}
                disabled={isLoading}>
                <GoogleIcon />
                Google
              </button>
              <button type="button"
                className="su-oauth flex h-11 flex-1 cursor-pointer items-center justify-center gap-2 rounded-[10px] border border-rule-strong bg-paper text-[13.5px] font-medium text-ink disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {/* TODO: GitHub OAuth */}}
                disabled={isLoading}>
                <GitHubIcon />
                GitHub
              </button>
            </div>

            {/* Divider */}
            <div className="mb-[22px] flex items-center gap-3">
              <span className="h-px flex-1 bg-rule" />
              <span className="whitespace-nowrap text-[12px] uppercase tracking-[0.05em] text-ink-3">
                or sign up with email
              </span>
              <span className="h-px flex-1 bg-rule" />
            </div>

            {/* Name row */}
            <div className="mb-3.5 grid grid-cols-2 gap-3">
              <Field id="fname" label="First name" placeholder="Ada"
                autoComplete="given-name" value={firstName} onChange={setFirstName} />
              <Field id="lname" label="Last name" placeholder="Lovelace"
                autoComplete="family-name" value={lastName} onChange={setLastName} />
            </div>

            {/* Email */}
            <div className="mb-3.5">
              <Field id="email" label="Email address" type="email"
                placeholder="you@company.com" autoComplete="email"
                value={email} onChange={setEmail} />
            </div>

            {/* Password + strength */}
            <div className="mb-3.5">
              <Field
                id="password"
                label="Password"
                type={showPw ? "text" : "password"}
                placeholder="Min. 8 characters"
                autoComplete="new-password"
                value={password}
                onChange={setPassword}
                rightSlot={
                  <button type="button"
                    className="su-pw-toggle flex items-center border-none bg-transparent p-0 text-ink-3"
                    onClick={() => setShowPw((v) => !v)}
                    aria-label={showPw ? "Hide password" : "Show password"}>
                    {showPw ? <EyeClosed /> : <EyeOpen />}
                  </button>
                }
                hint={
                  password.length > 0 ? (
                    <div className="mt-2">
                      {/* Bars */}
                      <div className="mb-[5px] flex gap-1" role="meter"
                        aria-label={`Password strength: ${strength.label}`}
                        aria-valuenow={strength.score} aria-valuemin={0} aria-valuemax={4}>
                        {[0,1,2,3].map((i) => (
                          <div key={i} className="su-bar"
                            style={{
                              background: i < strength.score
                                ? STRENGTH_COLORS[strength.level]
                                : "#E0D7C2",
                            }}
                          />
                        ))}
                      </div>
                      {/* Label */}
                      <span className="text-[11.5px] transition-colors duration-300"
                        style={{ color: STRENGTH_COLORS[strength.level] }}>
                        {strength.label}
                      </span>
                    </div>
                  ) : null
                }
              />
            </div>

            {/* Confirm password */}
            <div className="mb-1">
              <Field
                id="confirm"
                label="Confirm password"
                type={showConfirm ? "text" : "password"}
                placeholder="Re-enter your password"
                autoComplete="new-password"
                value={confirm}
                onChange={setConfirm}
                rightSlot={
                  <button type="button"
                    className="su-pw-toggle flex items-center border-none bg-transparent p-0 text-ink-3"
                    onClick={() => setShowConfirm((v) => !v)}
                    aria-label={showConfirm ? "Hide password" : "Show password"}>
                    {showConfirm ? <EyeClosed /> : <EyeOpen />}
                  </button>
                }
              />
              {/* Match hint */}
              <div
                className="mt-1.5 min-h-[16px] text-[11.5px] transition-colors duration-200"
                style={{
                  color: matchState === "ok" ? "#134E3A"
                       : matchState === "no" ? "#C95A3D"
                       : "transparent",
                }}
                role="alert"
                aria-live="polite"
              >
                {matchLabel || " "}
              </div>
            </div>

            {/* Terms */}
            <div className="mb-5 mt-4 flex items-start gap-2.5">
              <input
                id="terms"
                type="checkbox"
                checked={terms}
                onChange={(e) => setTerms(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded-[4px] border border-rule-strong"
                style={{ accentColor: "#134E3A" }}
              />
              <label htmlFor="terms" className="cursor-pointer text-[13px] leading-[1.5] text-ink-2">
                I agree to Career Roadmap AI&apos;s{" "}
                <Link href="/terms"
                  className="border-b border-green-soft font-medium text-green transition-[border-color] hover:border-green">
                  Terms of Service
                </Link>{" "}
                and{" "}
                <Link href="/privacy"
                  className="border-b border-green-soft font-medium text-green transition-[border-color] hover:border-green">
                  Privacy Policy
                </Link>
                . I understand my data will be used to personalise my career roadmap.
              </label>
            </div>

            {/* Submit */}
            <button
              type="submit"
              onClick={handleSubmit}
              disabled={!terms || isLoading || matchState === "no"}
              className="su-btn-primary flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-green text-[15px] font-semibold tracking-[0.01em] text-bg disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? (
                <svg className="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  aria-hidden="true">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  aria-hidden="true">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                  <line x1="19" y1="8" x2="19" y2="14"/>
                  <line x1="22" y1="11" x2="16" y2="11"/>
                </svg>
              )}
              {isLoading ? "Creating account…" : "Create my account"}
            </button>

            {/* Footer */}
            <p className="mt-5 text-center text-[12px] leading-[1.6] text-ink-3">
              Already have an account?{" "}
              <Link href="/login"
                className="border-b border-rule text-ink-2 transition-colors hover:text-ink">
                Sign in
              </Link>
            </p>

          </div>
        </div>
      </div>
    </>
  );
}