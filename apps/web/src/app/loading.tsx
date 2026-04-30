export default function Loading() {
  return (
    <>
      <style>{`
        /* Path draw-on animation */
        @keyframes draw {
          from { stroke-dashoffset: 52; }
          to   { stroke-dashoffset: 0;  }
        }
        /* Node pop-in with elastic bounce */
        @keyframes popIn {
          0%   { transform: scale(0); opacity: 0; }
          60%  { transform: scale(1.35); opacity: 1; }
          80%  { transform: scale(0.88); }
          100% { transform: scale(1); opacity: 1; }
        }
        /* Wordmark fade-slide up */
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0);    }
        }
        /* Pulse ring */
        @keyframes ringPulse {
          0%   { transform: scale(0.92); opacity: 0.5; }
          50%  { transform: scale(1.08); opacity: 0.15; }
          100% { transform: scale(0.92); opacity: 0.5; }
        }
        /* Dot bounce stagger */
        @keyframes dotBounce {
          0%, 80%, 100% { transform: translateY(0);    opacity: 0.35; }
          40%            { transform: translateY(-5px); opacity: 1;    }
        }
        /* Subtle shimmer on the rule line */
        @keyframes shimmer {
          0%   { background-position: -200% center; }
          100% { background-position:  200% center; }
        }

        .loading-path {
          stroke-dasharray: 52;
          stroke-dashoffset: 52;
          animation: draw 1.1s cubic-bezier(0.4, 0, 0.2, 1) 0.2s forwards;
        }
        .node-terra {
          transform-origin: 3px 22px;
          opacity: 0;
          animation: popIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 1.1s forwards;
        }
        .node-green {
          transform-origin: 14px 6px;
          opacity: 0;
          animation: popIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 1.25s forwards;
        }
        .node-ink {
          transform-origin: 25px 22px;
          opacity: 0;
          animation: popIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 1.4s forwards;
        }
        .ring-pulse {
          animation: ringPulse 2.4s ease-in-out 1.6s infinite;
        }
        .wordmark {
          opacity: 0;
          animation: fadeUp 0.7s ease-out 1.5s forwards;
        }
        .caption {
          opacity: 0;
          animation: fadeUp 0.7s ease-out 1.75s forwards;
        }
        .dot-1 { animation: dotBounce 1.2s ease-in-out 1.9s infinite; }
        .dot-2 { animation: dotBounce 1.2s ease-in-out 2.05s infinite; }
        .dot-3 { animation: dotBounce 1.2s ease-in-out 2.2s infinite; }
        .rule-shimmer {
          opacity: 0;
          animation: fadeUp 0.5s ease-out 1.6s forwards;
          background: linear-gradient(
            90deg,
            transparent 0%,
            #C9BFA7 30%,
            #C95A3D 50%,
            #C9BFA7 70%,
            transparent 100%
          );
          background-size: 200% auto;
          animation:
            fadeUp 0.5s ease-out 1.6s forwards,
            shimmer 2.4s linear 2.1s infinite;
        }
      `}</style>

      <div
        role="status"
        aria-label="Loading"
        className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-bg px-6"
      >
        {/* Subtle radial backdrop */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 60% 50% at 50% 40%, rgba(19,78,58,0.055) 0%, transparent 70%)",
          }}
        />

        {/* Corner ornaments */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-8 top-8 font-serif text-2xl font-light text-rule-strong select-none opacity-60"
        >
          ✦
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-8 right-8 font-serif text-2xl font-light text-rule-strong select-none opacity-60"
        >
          ✦
        </span>

        {/* Logo + ring */}
        <div className="relative mb-8 flex items-center justify-center">
          {/* Pulse ring */}
          <div
            aria-hidden="true"
            className="ring-pulse absolute h-24 w-24 rounded-full border border-rule-strong"
          />

          {/* Logo mark */}
          <svg
            viewBox="0 0 28 28"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="relative h-14 w-14"
            aria-hidden="true"
          >
            <path
              className="loading-path"
              d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
              stroke="#15140F"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <circle className="node-terra" cx="3"  cy="22" r="2.2" fill="#C95A3D" />
            <circle className="node-green" cx="14" cy="6"  r="2.2" fill="#134E3A" />
            <circle className="node-ink"   cx="25" cy="22" r="2.2" fill="#15140F" />
          </svg>
        </div>

        {/* Wordmark */}
        <p className="wordmark mb-3 font-serif text-2xl font-medium tracking-[-0.02em] text-ink">
          Career Roadmap <em className="italic text-green">AI</em>
        </p>

        {/* Shimmer rule */}
        <div
          aria-hidden="true"
          className="rule-shimmer mb-5 h-px w-32 rounded-full"
        />

        {/* Caption + dots */}
        <div className="caption flex items-center gap-2.5">
          <span className="text-[13px] font-medium tracking-[0.06em] text-ink-3 uppercase">
            Preparing your workspace
          </span>
          <span className="flex items-center gap-1 pt-px" aria-hidden="true">
            <span className="dot-1 inline-block h-1 w-1 rounded-full bg-terra" />
            <span className="dot-2 inline-block h-1 w-1 rounded-full bg-terra" />
            <span className="dot-3 inline-block h-1 w-1 rounded-full bg-terra" />
          </span>
        </div>
      </div>
    </>
  );
}