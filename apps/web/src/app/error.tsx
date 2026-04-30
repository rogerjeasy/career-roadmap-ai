"use client";

import { useEffect } from "react";
import Link from "next/link";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Wire up to Sentry / your error tracker here
    console.error(error);
  }, [error]);

  return (
    <>
      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0);    }
        }
        @keyframes scaleIn {
          from { opacity: 0; transform: scale(0.94); }
          to   { opacity: 1; transform: scale(1);    }
        }
        @keyframes drift {
          0%   { transform: translateY(0px)   rotate(0deg);   }
          33%  { transform: translateY(-8px)  rotate(1.5deg); }
          66%  { transform: translateY(4px)   rotate(-1deg);  }
          100% { transform: translateY(0px)   rotate(0deg);   }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(-8px); }
          to   { opacity: 1; transform: translateX(0);    }
        }

        .err-ornament {
          animation: drift 7s ease-in-out infinite;
        }
        .err-pill  { animation: scaleIn 0.55s cubic-bezier(0.34,1.2,0.64,1) 0.1s both; }
        .err-head  { animation: fadeUp  0.6s ease-out 0.2s both; }
        .err-rule  { animation: scaleIn 0.5s ease-out 0.35s both; }
        .err-body  { animation: fadeUp  0.6s ease-out 0.42s both; }
        .err-code  { animation: slideIn 0.5s ease-out 0.5s both; }
        .err-ctas  { animation: fadeUp  0.6s ease-out 0.56s both; }

        .btn-primary {
          transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
        }
        .btn-primary:hover {
          background: #0E3A2B;
          transform: translateY(-1px);
          box-shadow: 0 6px 20px -4px rgba(19,78,58,0.4);
        }
        .btn-ghost {
          transition: background 0.2s ease, border-color 0.2s ease;
        }
        .btn-ghost:hover {
          background: #EFE8D7;
          border-color: #15140F;
        }
        .btn-primary .arrow,
        .btn-ghost   .arrow {
          display: inline-block;
          transition: transform 0.2s ease;
        }
        .btn-primary:hover .arrow,
        .btn-ghost:hover   .arrow { transform: translateX(3px); }
      `}</style>

      <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-bg px-6 py-20">

        {/* Ambient radial — warm green tint */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 55% 45% at 50% 35%, rgba(201,90,61,0.06) 0%, transparent 70%)",
          }}
        />

        {/* Corner ornament TL */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-8 top-8 select-none font-serif text-xl font-light text-rule-strong opacity-50"
        >
          ✦
        </span>
        {/* Corner ornament BR */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-8 right-8 select-none font-serif text-xl font-light text-rule-strong opacity-50"
        >
          ✦
        </span>

        {/* Vertical centre-line (decorative) */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2"
          style={{ background: "linear-gradient(to bottom, transparent, #E0D7C2 20%, #E0D7C2 80%, transparent)" }}
        />

        <div className="relative z-10 flex w-full max-w-lg flex-col items-center text-center">

          {/* Status pill */}
          <div className="err-pill mb-8 inline-flex items-center gap-2 rounded-full border border-terra-soft bg-terra-faint px-4 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-terra" aria-hidden="true" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-terra-2">
              System error
            </span>
          </div>

          {/* Drifting ornament */}
          <p
            aria-hidden="true"
            className="err-ornament mb-4 select-none font-serif text-[72px] leading-none text-rule-strong sm:text-[96px]"
          >
            ✺
          </p>

          {/* Heading */}
          <h1 className="err-head mb-4 font-serif text-3xl font-medium leading-tight tracking-[-0.025em] text-ink sm:text-4xl">
            Something went{" "}
            <em className="italic text-terra">wrong</em>
          </h1>

          {/* Horizontal rule */}
          <div
            aria-hidden="true"
            className="err-rule mb-6 h-px w-16 rounded-full bg-rule-strong"
          />

          {/* Error message */}
          <p className="err-body mb-2 max-w-sm text-[15px] leading-relaxed text-ink-2">
            {error.message && error.message !== "undefined"
              ? error.message
              : "An unexpected error occurred. Our team has been notified and is looking into it."}
          </p>

          {/* Digest — for support reference */}
          {error.digest && (
            <p className="err-code mb-8 font-mono text-[11px] tracking-widest text-ink-3">
              ref: {error.digest}
            </p>
          )}
          {!error.digest && <div className="mb-8" />}

          {/* CTAs */}
          <div className="err-ctas flex flex-col items-center gap-3 sm:flex-row sm:gap-4">
            <button
              onClick={reset}
              className="btn-primary inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-6 py-3 text-sm font-medium text-bg sm:w-auto"
            >
              Try again
              <span className="arrow">→</span>
            </button>

            <Link
              href="/"
              className="btn-ghost inline-flex w-full items-center justify-center gap-2 rounded-full border border-rule-strong bg-transparent px-6 py-3 text-sm font-medium text-ink-2 sm:w-auto"
            >
              Return home
              <span className="arrow">→</span>
            </Link>
          </div>

          {/* Support hint */}
          <p className="mt-10 text-[12px] text-ink-3">
            Persisting?{" "}
            <a
              href="mailto:support@careerroadmap.ai"
              className="text-green underline underline-offset-[3px] transition-colors hover:text-green-2"
            >
              Contact support
            </a>
          </p>

        </div>
      </div>
    </>
  );
}