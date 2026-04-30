import Link from "next/link";

export default function NotFound() {
  return (
    <>
      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0);    }
        }
        @keyframes scaleIn {
          from { opacity: 0; transform: scale(0.92); }
          to   { opacity: 1; transform: scale(1);    }
        }
        @keyframes driftSlow {
          0%   { transform: translateY(0px)  rotate(0deg);   }
          30%  { transform: translateY(-9px) rotate(1.2deg); }
          65%  { transform: translateY(5px)  rotate(-0.8deg);}
          100% { transform: translateY(0px)  rotate(0deg);   }
        }
        @keyframes drawPath {
          from { stroke-dashoffset: 52; }
          to   { stroke-dashoffset: 0;  }
        }
        @keyframes popIn {
          0%   { transform: scale(0); opacity: 0; }
          60%  { transform: scale(1.35); opacity: 1; }
          80%  { transform: scale(0.88); }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes shimmer {
          0%   { background-position: -200% center; }
          100% { background-position:  200% center; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }

        /* Logo */
        .nf-path {
          stroke-dasharray: 52;
          stroke-dashoffset: 52;
          animation: drawPath 1.1s cubic-bezier(0.4,0,0.2,1) 0.3s forwards;
        }
        .nf-node-terra {
          transform-origin: 3px 22px;
          opacity: 0;
          animation: popIn 0.5s cubic-bezier(0.34,1.56,0.64,1) 1.2s forwards;
        }
        .nf-node-green {
          transform-origin: 14px 6px;
          opacity: 0;
          animation: popIn 0.5s cubic-bezier(0.34,1.56,0.64,1) 1.35s forwards;
        }
        .nf-node-ink {
          transform-origin: 25px 22px;
          opacity: 0;
          animation: popIn 0.5s cubic-bezier(0.34,1.56,0.64,1) 1.5s forwards;
        }

        /* Content stagger */
        .nf-badge   { animation: scaleIn 0.5s cubic-bezier(0.34,1.2,0.64,1) 0.15s both; }
        .nf-404     { animation: fadeUp  0.7s ease-out 0.25s both; }
        .nf-divider { animation: scaleIn 0.5s ease-out 0.38s both; }
        .nf-heading { animation: fadeUp  0.65s ease-out 0.45s both; }
        .nf-body    { animation: fadeUp  0.65s ease-out 0.57s both; }
        .nf-ctas    { animation: fadeUp  0.65s ease-out 0.68s both; }
        .nf-footer  { animation: fadeUp  0.55s ease-out 0.80s both; }

        /* Drifting ornament */
        .nf-drift   { animation: driftSlow 9s ease-in-out infinite; }

        /* Shimmer on the large 404 */
        .nf-404-text {
          background: linear-gradient(
            90deg,
            #C9BFA7 0%,
            #15140F 35%,
            #C95A3D 50%,
            #15140F 65%,
            #C9BFA7 100%
          );
          background-size: 250% auto;
          -webkit-background-clip: text;
          background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: shimmer 5s linear 1s infinite;
        }

        /* Cursor blink on path endpoint */
        .nf-cursor { animation: blink 1.1s step-end 1.6s infinite; }

        /* Button transitions */
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

        /* Suggested links */
        .nf-link {
          transition: color 0.15s ease, padding-left 0.2s ease;
        }
        .nf-link:hover { color: #15140F; padding-left: 6px; }
      `}</style>

      <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-bg px-6 py-20">

        {/* Ambient backdrop — terra warmth */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 60% 50% at 50% 38%, rgba(182,138,46,0.07) 0%, transparent 70%)",
          }}
        />

        {/* Vertical centre-line */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2"
          style={{
            background:
              "linear-gradient(to bottom, transparent, #E0D7C2 15%, #E0D7C2 85%, transparent)",
          }}
        />

        {/* Corner ornaments */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-8 top-8 select-none font-serif text-xl font-light text-rule-strong opacity-50"
        >
          ✦
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-8 right-8 select-none font-serif text-xl font-light text-rule-strong opacity-50"
        >
          ✦
        </span>

        <div className="relative z-10 flex w-full max-w-lg flex-col items-center text-center">

          {/* Status badge */}
          <div className="nf-badge mb-8 inline-flex items-center gap-2 rounded-full border border-gold-soft bg-gold-soft px-4 py-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full bg-gold"
              aria-hidden="true"
            />
            <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-gold">
              Page not found
            </span>
          </div>

          {/* Animated logo mark */}
          <div className="relative mb-6 flex items-center justify-center">
            <svg
              viewBox="0 0 28 28"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="h-10 w-10"
              aria-hidden="true"
            >
              <path
                className="nf-path"
                d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
                stroke="#15140F"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
              <circle className="nf-node-terra" cx="3"  cy="22" r="2.2" fill="#C95A3D" />
              <circle className="nf-node-green" cx="14" cy="6"  r="2.2" fill="#134E3A" />
              <circle className="nf-node-ink"   cx="25" cy="22" r="2.2" fill="#15140F" />
              {/* Blinking cursor at path end — the destination was never reached */}
              <rect
                className="nf-cursor"
                x="26.5" y="19.5"
                width="1.4" height="5"
                rx="0.7"
                fill="#C95A3D"
              />
            </svg>
          </div>

          {/* Drifting ornament */}
          <p
            aria-hidden="true"
            className="nf-drift mb-2 select-none font-serif text-[64px] leading-none text-rule-strong sm:text-[80px]"
          >
            ✺
          </p>

          {/* 404 — shimmer gradient text */}
          <p className="nf-404 mb-3 font-serif font-medium leading-none tracking-[-0.04em]">
            <span
              className="nf-404-text text-[88px] sm:text-[112px]"
              aria-label="404"
            >
              404
            </span>
          </p>

          {/* Divider */}
          <div
            aria-hidden="true"
            className="nf-divider mb-6 h-px w-16 rounded-full bg-rule-strong"
          />

          {/* Heading */}
          <h1 className="nf-heading mb-4 font-serif text-2xl font-medium leading-snug tracking-[-0.02em] text-ink sm:text-3xl">
            This destination{" "}
            <em className="italic text-gold">doesn&apos;t exist</em>
          </h1>

          {/* Body */}
          <p className="nf-body mb-8 max-w-sm text-[15px] leading-relaxed text-ink-2">
            The page you&apos;re looking for may have moved, been removed, or
            the URL might be incorrect. Let&apos;s get you back on track.
          </p>

          {/* CTAs */}
          <div className="nf-ctas flex w-full flex-col items-center gap-3 sm:flex-row sm:justify-center sm:gap-4">
            <Link
              href="/"
              className="btn-primary inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-6 py-3 text-sm font-medium text-bg sm:w-auto"
            >
              Back to home
              <span className="arrow">→</span>
            </Link>

            <Link
              href="/dashboard"
              className="btn-ghost inline-flex w-full items-center justify-center gap-2 rounded-full border border-rule-strong bg-transparent px-6 py-3 text-sm font-medium text-ink-2 sm:w-auto"
            >
              Go to dashboard
              <span className="arrow">→</span>
            </Link>
          </div>

          {/* Quick links */}
          <div className="nf-footer mt-12 w-full border-t border-rule pt-8">
            <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">
              You might be looking for
            </p>
            <ul className="flex flex-col items-center gap-2 sm:flex-row sm:justify-center sm:gap-8">
              {[
                { label: "My Roadmap",   href: "/roadmap"      },
                { label: "Schedule",     href: "/schedule"     },
                { label: "Progress",     href: "/progress"     },
                { label: "CV Analysis",  href: "/cv-analysis"  },
                { label: "Coach",        href: "/coach"        },
              ].map(({ label, href }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="nf-link text-[13px] font-medium text-ink-3"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

        </div>
      </div>
    </>
  );
}