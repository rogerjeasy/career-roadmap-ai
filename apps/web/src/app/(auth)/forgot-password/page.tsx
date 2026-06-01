"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { sendPasswordResetEmail } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { ROUTES } from "@/lib/constants";

function LogoMark() {
  return (
    <svg viewBox="0 0 28 28" fill="none" aria-hidden="true" className="h-8 w-8 shrink-0">
      <path d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22" stroke="#15140F" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="3" cy="22" r="2.2" fill="#C95A3D" />
      <circle cx="14" cy="6" r="2.2" fill="#134E3A" />
      <circle cx="25" cy="22" r="2.2" fill="#15140F" />
    </svg>
  );
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("sending");
    setError(null);
    try {
      await sendPasswordResetEmail(firebaseAuth, email.trim());
      setStatus("sent");
    } catch {
      // Don't reveal whether the address exists — show a neutral success state.
      setStatus("sent");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-5 py-12">
      <div className="w-full max-w-[400px]">
        <Link href={ROUTES.home} className="mb-8 flex items-center gap-2.5 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
          <LogoMark />
          Roadmap
        </Link>

        <div className="rounded-[16px] border border-rule bg-paper p-8">
          {status === "sent" ? (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-faint text-green-2">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-6 w-6" aria-hidden="true">
                  <path d="M4 6h16v12H4z" />
                  <path d="m4 7 8 6 8-6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <h1 className="font-serif text-[22px] font-medium tracking-[-0.01em] text-ink">Check your inbox</h1>
              <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">
                If an account exists for <span className="font-medium text-ink">{email}</span>, we&apos;ve sent a link to reset your password.
              </p>
              <Link
                href={ROUTES.login}
                className="mt-6 inline-flex w-full items-center justify-center rounded-[10px] bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
              >
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              <h1 className="font-serif text-[24px] font-medium tracking-[-0.02em] text-ink">Reset your password</h1>
              <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">
                Enter your email and we&apos;ll send you a link to set a new password.
              </p>

              <form onSubmit={onSubmit} className="mt-6 space-y-4">
                <label className="block">
                  <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Email</span>
                  <input
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    className="w-full rounded-[10px] border border-rule-strong bg-paper px-3.5 py-3 text-[14px] text-ink placeholder:text-ink-3 focus:border-green focus:outline-none"
                  />
                </label>
                {error && <p className="text-[12.5px] text-terra-2">{error}</p>}
                <button
                  type="submit"
                  disabled={status === "sending" || !email.trim()}
                  className="inline-flex w-full items-center justify-center rounded-[10px] bg-ink px-5 py-3 text-[14px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-60"
                >
                  {status === "sending" ? "Sending…" : "Send reset link"}
                </button>
              </form>

              <p className="mt-6 text-center text-[13px] text-ink-3">
                Remembered it?{" "}
                <Link href={ROUTES.login} className="font-medium text-terra hover:text-terra-2">
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
