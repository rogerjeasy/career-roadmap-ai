"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";

// ─── Logo mark SVG (light version for dark background) ────────────────────────
function LogoMark() {
  return (
    <svg viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg"
      className="w-8 h-8 shrink-0" aria-hidden="true">
      <path d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
        stroke="#F7F2E8" strokeWidth="1.6" strokeLinecap="round"/>
      <circle cx="3"  cy="22" r="2.2" fill="#C95A3D"/>
      <circle cx="14" cy="6"  r="2.2" fill="#DCE7DC"/>
      <circle cx="25" cy="22" r="2.2" fill="#F7F2E8"/>
    </svg>
  );
}

// ─── Eye icon (open) ──────────────────────────────────────────────────────────
function EyeOpen() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}

// ─── Eye icon (closed) ────────────────────────────────────────────────────────
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

// ─── Google SVG ───────────────────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M17.64 9.2045c0-.638-.0573-1.252-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087C16.6582 14.252 17.64 11.9455 17.64 9.2045z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8055.54-1.8368.859-3.0477.859-2.344 0-4.3282-1.5836-5.036-3.7104H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z" fill="#34A853"/>
      <path d="M3.964 10.71c-.18-.54-.2827-1.1168-.2827-1.71s.1027-1.17.2827-1.71V4.9582H.9573C.3477 6.1732 0 7.5477 0 9s.3477 2.8268.9573 4.0418L3.964 10.71z" fill="#FBBC05"/>
      <path d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5813C13.4627.8918 11.4255 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.964 7.29C4.6718 5.1632 6.656 3.5795 9 3.5795z" fill="#EA4335"/>
    </svg>
  );
}

// ─── GitHub SVG ───────────────────────────────────────────────────────────────
function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
  );
}

// ─── Steps data ───────────────────────────────────────────────────────────────
const STEPS = [
  {
    num: "1",
    title: "Map your trajectory",
    body:  "Visualise where you are and where you’re headed.",
  },
  {
    num: "2",
    title: "Identify skill gaps",
    body:  "AI pinpoints exactly what to learn next.",
  },
  {
    num: "3",
    title: "Execute with confidence",
    body:  "Step-by-step plans tailored to your timeline.",
  },
];

// ─── Page component ───────────────────────────────────────────────────────────
export default function SignInPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember]         = useState(false);
  const [email, setEmail]               = useState("");
  const [password, setPassword]         = useState("");
  const [isLoading, setIsLoading]       = useState(false);

  const { loginWithEmail, loginWithGoogle } = useAuth();

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setIsLoading(true);
    try {
      await loginWithEmail(email, password, remember);
    } finally {
      setIsLoading(false);
    }
  }, [email, password, remember, loginWithEmail]);

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
        /* Noise grain overlay */
        .grain::before {
          content: "";
          position: fixed; inset: 0; z-index: 9999; pointer-events: none; opacity: .032;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
          background-size: 128px 128px;
        }

        /* Left panel ambient + rings */
        .left-panel-bg::before {
          content: "";
          position: absolute; inset: 0;
          background:
            radial-gradient(ellipse 80% 70% at 30% 60%, #1e3d2f 0%, transparent 70%),
            radial-gradient(ellipse 60% 50% at 70% 20%, #3a1a0e 0%, transparent 60%);
          opacity: 0.7;
          pointer-events: none;
        }
        .left-panel-bg::after {
          content: "";
          position: absolute;
          width: 520px; height: 520px;
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 50%;
          bottom: -180px; right: -180px;
          pointer-events: none;
        }

        /* Fade-up entrance */
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .anim-form   { animation: fadeUp .6s cubic-bezier(.2,.7,.2,1) both; }
        .anim-left-t { animation: fadeUp .7s cubic-bezier(.2,.7,.2,1) .1s both; }
        .anim-left-b { animation: fadeUp .7s cubic-bezier(.2,.7,.2,1) .25s both; }

        /* OAuth button hover */
        .oauth-btn {
          transition: background .15s, border-color .15s, transform .12s;
        }
        .oauth-btn:hover {
          background: #EFE8D7;
          border-color: #8A8170;
          transform: translateY(-1px);
        }
        .oauth-btn:active { transform: translateY(0); }

        /* Input focus ring */
        .field-input:focus {
          border-color: #134E3A !important;
          box-shadow: 0 0 0 3px rgba(19,78,58,0.1);
          outline: none;
        }
        .field-input:hover:not(:focus) { border-color: #8A8170; }

        /* Primary button */
        .btn-primary-signin {
          transition: background .2s ease, transform .12s ease;
          position: relative; overflow: hidden;
        }
        .btn-primary-signin::after {
          content: "";
          position: absolute; inset: 0;
          background: linear-gradient(135deg, rgba(255,255,255,0.06) 0%, transparent 60%);
          pointer-events: none;
        }
        .btn-primary-signin:hover { background: #0E3A2B !important; transform: translateY(-1px); }
        .btn-primary-signin:active { transform: translateY(0); }

        /* Forgot link underline */
        .forgot-link { border-bottom: 1px solid #F4DDD2; transition: border-color .15s; }
        .forgot-link:hover { border-color: #C95A3D; }

        /* Register link underline */
        .register-link { border-bottom: 1px solid #DCE7DC; font-weight: 500; color: #134E3A; transition: border-color .15s; }
        .register-link:hover { border-color: #134E3A; }

        /* Footer links */
        .footer-link { border-bottom: 1px solid #E0D7C2; color: #4D4639; transition: color .15s; }
        .footer-link:hover { color: #15140F; }

        /* Password toggle */
        .pw-toggle { transition: color .15s; }
        .pw-toggle:hover { color: #15140F; }
      `}</style>

      {/* Shell */}
      <div className="grain signin-shell min-h-screen" style={{ display: "grid", gridTemplateColumns: "1fr 1fr" }}>
        <style>{`
          @media (max-width: 800px) {
            .signin-shell { grid-template-columns: 1fr !important; }
            .signin-left  { display: none !important; }
            .signin-right { padding: 48px 24px !important; }
          }
        `}</style>

        {/* ══════ LEFT PANEL ══════ */}
        <div
          className="signin-left left-panel-bg relative overflow-hidden"
          style={{
            background: "#15140F",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "48px 56px",
          }}
        >
          {/* Decorative rings */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute rounded-full"
            style={{ width: 360, height: 360, border: "1px solid rgba(255,255,255,0.05)", bottom: -90, right: -90 }}
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute rounded-full"
            style={{ width: 200, height: 200, border: "1px solid rgba(255,255,255,0.07)", bottom: -20, right: -20 }}
          />

          {/* Logo */}
          <div className="anim-left-t relative z-10">
            <Link
              href="/"
              className="inline-flex items-center gap-2.5 font-serif text-[20px] font-semibold tracking-[-0.01em] text-bg no-underline"
              aria-label="Career Roadmap AI — home"
            >
              <LogoMark />
              Career Roadmap AI
            </Link>
          </div>

          {/* Tagline + steps */}
          <div className="anim-left-b relative z-10">
            {/* Quote */}
            <p
              className="mb-7 font-serif font-[300] leading-[1.12] tracking-[-0.025em] text-bg"
              style={{ fontSize: "clamp(34px, 4vw, 52px)" }}
            >
              Your career,<br />
              <em className="italic" style={{ color: "#F4DDD2" }}>designed</em><br />
              with intelligence.
            </p>

            {/* Sub */}
            <p className="text-[14px] leading-[1.6]" style={{ color: "rgba(247,242,232,0.52)", maxWidth: 340 }}>
              Join thousands of professionals navigating their paths with
              AI-powered clarity and precision.
            </p>

            {/* Steps */}
            <div className="mt-11 flex flex-col gap-[18px]">
              {STEPS.map(({ num, title, body }) => (
                <div key={num} className="flex items-start gap-3.5">
                  {/* Number circle */}
                  <div
                    className="mt-px flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px]"
                    style={{
                      border: "1px solid rgba(247,242,232,0.2)",
                      color: "rgba(247,242,232,0.5)",
                    }}
                    aria-hidden="true"
                  >
                    {num}
                  </div>
                  {/* Text */}
                  <div>
                    <strong
                      className="mb-0.5 block text-[13.5px] font-medium"
                      style={{ color: "rgba(247,242,232,0.9)" }}
                    >
                      {title}
                    </strong>
                    <span className="text-[13px] leading-[1.5]" style={{ color: "rgba(247,242,232,0.6)" }}>
                      {body}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ══════ RIGHT PANEL ══════ */}
        <div
          className="signin-right flex flex-col items-center justify-center bg-bg"
          style={{ padding: "64px 48px" }}
        >
          <form className="anim-form w-full" style={{ maxWidth: 400 }} onSubmit={handleSubmit}>

            {/* Form header */}
            <div className="mb-9">
              <h1
                className="mb-2 font-serif font-[400] leading-[1.1] tracking-[-0.025em] text-ink"
                style={{ fontSize: 34 }}
              >
                Welcome <em className="italic text-terra">back</em>
              </h1>
              <p className="text-[14px] leading-[1.5] text-ink-3">
                Don&apos;t have an account?{" "}
                <Link href="/register" className="register-link">
                  Create one — it&apos;s free
                </Link>
              </p>
            </div>

            {/* OAuth buttons */}
            <div className="mb-7 flex flex-col gap-2.5">
              <button
                type="button"
                className="oauth-btn flex h-[46px] w-full cursor-pointer items-center justify-center gap-2.5 rounded-[10px] border border-rule-strong bg-paper text-[14px] font-medium text-ink disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleGoogle}
                disabled={isLoading}
              >
                <GoogleIcon />
                Continue with Google
              </button>

              <button
                type="button"
                className="oauth-btn flex h-[46px] w-full cursor-pointer items-center justify-center gap-2.5 rounded-[10px] border border-rule-strong bg-paper text-[14px] font-medium text-ink disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {/* TODO: GitHub OAuth */}}
                disabled={isLoading}
              >
                <GitHubIcon />
                Continue with GitHub
              </button>
            </div>

            {/* Divider */}
            <div className="mb-7 flex items-center gap-3">
              <span className="h-px flex-1 bg-rule" />
              <span className="whitespace-nowrap text-[12px] uppercase tracking-[0.05em] text-ink-3">
                or sign in with email
              </span>
              <span className="h-px flex-1 bg-rule" />
            </div>

            {/* Email field */}
            <div className="mb-[18px]">
              <label
                htmlFor="email"
                className="mb-[7px] block text-[12.5px] font-medium tracking-[0.02em] text-ink-2"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@company.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="field-input w-full rounded-[10px] border border-rule-strong bg-paper px-[14px] text-[14px] text-ink transition-[border-color,box-shadow] duration-150 placeholder:text-ink-3"
                style={{ height: 46 }}
              />
            </div>

            {/* Password field */}
            <div className="mb-[18px]">
              {/* Label row */}
              <div className="mb-[7px] flex items-center justify-between">
                <label
                  htmlFor="password"
                  className="text-[12.5px] font-medium tracking-[0.02em] text-ink-2"
                >
                  Password
                </label>
                <Link href="/forgot-password" className="forgot-link text-[12.5px] font-medium text-terra">
                  Forgot password?
                </Link>
              </div>

              {/* Input + toggle wrapper */}
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••••"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="field-input w-full rounded-[10px] border border-rule-strong bg-paper text-[14px] text-ink transition-[border-color,box-shadow] duration-150 placeholder:text-ink-3"
                  style={{ height: 46, paddingLeft: 14, paddingRight: 44 }}
                />
                <button
                  type="button"
                  className="pw-toggle absolute right-[14px] top-1/2 -translate-y-1/2 border-none bg-transparent p-0 text-ink-3"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeClosed /> : <EyeOpen />}
                </button>
              </div>
            </div>

            {/* Remember me */}
            <div className="mb-6 flex items-center gap-2">
              <input
                id="remember"
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 cursor-pointer rounded-[4px] border border-rule-strong"
                style={{ accentColor: "#134E3A" }}
              />
              <label
                htmlFor="remember"
                className="cursor-pointer select-none text-[13px] text-ink-2"
              >
                Keep me signed in for 30 days
              </label>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading || !email || !password}
              className="btn-primary-signin flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-green text-[15px] font-semibold tracking-[0.01em] text-bg disabled:cursor-not-allowed disabled:opacity-50"
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
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
                  <polyline points="10 17 15 12 10 7"/>
                  <line x1="15" y1="12" x2="3" y2="12"/>
                </svg>
              )}
              {isLoading ? "Signing in…" : "Sign in to your account"}
            </button>

            {/* Footer */}
            <p className="mt-7 text-center text-[12px] leading-[1.6] text-ink-3">
              By signing in you agree to our{" "}
              <Link href="/terms" className="footer-link">Terms of Service</Link>
              {" "}and{" "}
              <Link href="/privacy" className="footer-link">Privacy Policy</Link>
            </p>

          </form>
        </div>
      </div>
    </>
  );
}