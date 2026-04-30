import Link from "next/link";

// ─────────────────────────────────────────────────────────────────────────────
// Inline keyframes — CSS-only, no JS, works in Server Components
// ─────────────────────────────────────────────────────────────────────────────
const STYLES = `
  /* Hero text stagger */
  @keyframes heroin {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .hero-child { opacity: 0; animation: heroin 0.8s cubic-bezier(.2,.7,.2,1) forwards; }
  .h-d1 { animation-delay: 0.05s; }
  .h-d2 { animation-delay: 0.18s; }
  .h-d3 { animation-delay: 0.30s; }
  .h-d4 { animation-delay: 0.42s; }
  .h-d5 { animation-delay: 0.54s; }

  /* Eyebrow pulsing dot */
  @keyframes eyedot {
    0%,100% { box-shadow: 0 0 0 4px #F4DDD2; }
    50%      { box-shadow: 0 0 0 8px rgba(244,221,210,0.45); }
  }
  .eyedot { animation: eyedot 2.4s ease-in-out infinite; }

  /* Roadmap path draw-on */
  @keyframes drawpath { to { stroke-dashoffset: 0; } }
  .roadmap-path {
    stroke-dasharray: 1400;
    stroke-dashoffset: 1400;
    animation: drawpath 2.2s ease-out 0.4s forwards;
  }

  /* SVG milestones + labels */
  @keyframes fadein { to { opacity: 1; } }
  .ms { opacity: 0; animation: fadein .5s ease-out forwards; }

  /* Float cards slide up */
  @keyframes cardin {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .float-card {
    opacity: 0;
    animation: cardin .7s cubic-bezier(.2,.7,.2,1) forwards;
  }
  .fc-d1 { animation-delay: 1.2s; }
  .fc-d2 { animation-delay: 1.5s; }
  .fc-d3 { animation-delay: 1.8s; }
  .badge-score {
    opacity: 0;
    animation: cardin .7s cubic-bezier(.2,.7,.2,1) 2s forwards;
  }

  /* Progress bar fill */
  @keyframes fillbar { to { width: 57%; } }
  .progress-fill {
    width: 0;
    animation: fillbar 1.2s cubic-bezier(.4,0,.2,1) 1.8s forwards;
  }

  /* Live pulse dot */
  @keyframes livedot {
    0%,100% { opacity: 1; transform: scale(1); }
    50%     { opacity: 0.6; transform: scale(1.4); }
  }
  .live-dot { animation: livedot 2s ease-in-out infinite; }

  /* Trust bar marquee */
  @keyframes marquee {
    from { transform: translateX(0); }
    to   { transform: translateX(-50%); }
  }
  .marquee-track {
    animation: marquee 30s linear infinite;
    will-change: transform;
  }
  .marquee-track:hover { animation-play-state: paused; }

  /* Button hover */
  .btn-green {
    transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  }
  .btn-green:hover {
    background: #0E3A2B;
    transform: translateY(-1px);
    box-shadow: 0 6px 20px -4px rgba(19,78,58,0.45);
  }
  .btn-ghost-hero {
    transition: background 0.2s ease, border-color 0.2s ease;
  }
  .btn-ghost-hero:hover { background: #fff; border-color: #15140F; }

  .btn-green  .arrow { display:inline-block; transition: transform .2s; }
  .btn-green:hover  .arrow { transform: translateX(3px); }
`;

// ─── Data ────────────────────────────────────────────────────────────────────
const WEEK_TASKS = [
  { done: true,  label: "Finish RAG project pipeline",   time: "3.5h" },
  { done: true,  label: "Review system-design notes",    time: "2h"   },
  { done: false, label: "Mock interview · Anthropic",    time: "1h"   },
  { done: false, label: "Reach out to 3 ML engineers",   time: "45m"  },
] as const;

const MARKET_SKILLS = [
  { name: "RAG systems",    change: "↑ 38%" },
  { name: "PyTorch · prod", change: "↑ 21%" },
  { name: "Eval frameworks",change: "↑ 14%" },
] as const;

const TRUST_NAMES = [
  "The Verge", "TechCrunch", "Product Hunt", "Hacker News",
  "Indie Hackers", "WIRED", "MIT Technology Review", "Fast Company",
];

const AVATARS = [
  { letter: "M", bg: "#1F5A3D" },
  { letter: "R", bg: "#C95A3D" },
  { letter: "A", bg: "#B68A2E" },
  { letter: "K", bg: "#2A3A6E" },
];

// Checkmark SVG
function Check() {
  return (
    <svg width="9" height="9" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M2 6.5l3 3 5-7" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

// ─── Hero component ───────────────────────────────────────────────────────────
export function Hero() {
  return (
    <>
      <style>{STYLES}</style>

      {/* ── Hero section ─────────────────────────────────────────────── */}
      <section
        aria-label="Hero"
        className="mx-auto grid w-full max-w-[1440px] grid-cols-1 items-center gap-12 px-5 pb-10 pt-14 sm:px-10 sm:pt-20 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16 lg:px-12 lg:pb-10 lg:pt-[88px]"
      >

        {/* ── LEFT: Hero text ──────────────────────────────────────── */}
        <div className="flex flex-col">

          {/* Eyebrow */}
          <div className="hero-child h-d1 mb-7 inline-flex items-center gap-2.5">
            <span
              className="eyedot h-2 w-2 shrink-0 rounded-full bg-terra"
              aria-hidden="true"
            />
            <span className="text-[12px] font-medium uppercase tracking-[0.12em] text-green">
              The Global AI Career Platform
            </span>
          </div>

          {/* Headline */}
          <h1
            className="hero-child h-d2 mb-7 font-serif font-[350] leading-[0.96] tracking-[-0.035em] text-ink"
            style={{ fontSize: "clamp(40px, 7vw, 84px)" }}
          >
            Your career,{" "}
            <em
              className="italic text-green"
              style={{ fontStyle: "italic", fontVariationSettings: "\"opsz\" 144" }}
            >
              designed
            </em>{" "}
            &amp; tracked like an{" "}
            <span className="whitespace-nowrap">engineering project.</span>
          </h1>

          {/* Lede */}
          <p className="hero-child h-d3 mb-9 max-w-[520px] text-[16px] font-normal leading-[1.55] text-ink-2 sm:text-[18px]">
            Career Roadmap AI builds a living, intelligent career plan around
            your CV, your goals, and the real-time job market — then keeps it in
            sync with the world you&apos;re actually working in.
          </p>

          {/* CTAs */}
          <div className="hero-child h-d4 mb-9 flex flex-wrap items-center gap-3 sm:gap-4">
            <Link
              href="/register"
              className="btn-green inline-flex items-center gap-2 rounded-full bg-green px-6 py-[14px] text-[15px] font-medium text-white"
            >
              Start your roadmap
              <span className="arrow">→</span>
            </Link>

            <button
              type="button"
              className="btn-ghost-hero inline-flex items-center gap-2 rounded-full border border-rule-strong bg-transparent px-[22px] py-[13px] text-[15px] font-medium text-ink"
            >
              <svg
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-3.5 w-3.5 shrink-0"
                aria-hidden="true"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
              Watch 90s demo
            </button>
          </div>

          {/* Trust line */}
          <div className="hero-child h-d5 flex flex-wrap items-center gap-3.5 text-[13px] text-ink-3">
            {/* Avatar stack */}
            <div className="flex items-center" aria-label="Trusted by professionals worldwide">
              {AVATARS.map(({ letter, bg }) => (
                <span
                  key={letter}
                  className="-ml-2 first:ml-0 flex h-[26px] w-[26px] items-center justify-center rounded-full border-2 border-bg font-serif text-[11px] font-semibold text-white"
                  style={{ background: bg }}
                  aria-hidden="true"
                >
                  {letter}
                </span>
              ))}
              <span
                className="-ml-2 flex h-[26px] w-[26px] items-center justify-center rounded-full border-2 border-bg bg-ink font-serif text-[9px] font-semibold text-bg"
                aria-hidden="true"
              >
                +12K
              </span>
            </div>
            <p>Free to start. No credit card. Trusted by professionals in 84 countries.</p>
          </div>
        </div>

        {/* ── RIGHT: Hero visual (hidden below lg) ─────────────────── */}
        <div
          className="relative hidden lg:block"
          style={{ height: 580 }}
          aria-hidden="true"
        >

          {/* Career Health Score badge */}
          <div
            className="badge-score absolute right-[50px] top-[10px] z-20 flex items-center gap-2.5 rounded-full bg-ink py-2 pl-2 pr-3.5 text-[12px] font-medium text-bg"
          >
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
              style={{
                background:
                  "conic-gradient(#C95A3D 0deg 259deg, rgba(255,255,255,0.15) 259deg 360deg)",
              }}
            >
              <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-ink font-serif text-[11px] font-semibold">
                72
              </span>
            </div>
            Career Health Score
          </div>

          {/* Roadmap SVG */}
          <svg
            className="absolute inset-0 z-10 h-full w-full overflow-visible"
            viewBox="0 0 540 580"
            preserveAspectRatio="none"
          >
            {/* Main career path */}
            <path
              className="roadmap-path"
              d="M 40 540 C 40 460, 180 430, 200 360 C 220 290, 100 260, 130 200 C 160 140, 320 160, 360 110 C 400 60, 480 60, 500 40"
              fill="none"
              stroke="#134E3A"
              strokeWidth="1.5"
            />

            {/* Milestone: START */}
            <circle className="ms" cx="40"  cy="540" r="6" fill="#134E3A" stroke="#134E3A" strokeWidth="1.5" style={{ animationDelay: ".6s" }} />
            <text className="ms" x="56" y="544" style={{ fill: "#8A8170", fontSize: 10, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: "Geist, sans-serif", animationDelay: ".6s" }}>START · CV uploaded</text>

            {/* Milestone: FOUNDATION */}
            <circle className="ms" cx="200" cy="360" r="6" fill="#134E3A" stroke="#134E3A" strokeWidth="1.5" style={{ animationDelay: ".9s" }} />
            <text className="ms" x="216" y="364" style={{ fill: "#8A8170", fontSize: 10, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: "Geist, sans-serif", animationDelay: ".9s" }}>FOUNDATION</text>

            {/* Milestone: SPECIALISATION */}
            <circle className="ms" cx="130" cy="200" r="6" fill="#134E3A" stroke="#134E3A" strokeWidth="1.5" style={{ animationDelay: "1.2s" }} />
            <text className="ms" x="146" y="204" style={{ fill: "#8A8170", fontSize: 10, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: "Geist, sans-serif", animationDelay: "1.2s" }}>SPECIALISATION</text>

            {/* Milestone: PORTFOLIO (not yet done) */}
            <circle className="ms" cx="360" cy="110" r="6" fill="#F7F2E8" stroke="#134E3A" strokeWidth="1.5" style={{ animationDelay: "1.5s" }} />
            <text className="ms" x="376" y="114" style={{ fill: "#8A8170", fontSize: 10, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: "Geist, sans-serif", animationDelay: "1.5s" }}>PORTFOLIO</text>

            {/* Milestone: TARGET ROLE */}
            <circle className="ms" cx="500" cy="40" r="7" fill="#F7F2E8" stroke="#134E3A" strokeWidth="1.5" style={{ animationDelay: "1.8s" }} />
            <text className="ms" x="494" y="24" style={{ fill: "#8A8170", fontSize: 10, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: "Geist, sans-serif", animationDelay: "1.8s" }}>TARGET ROLE</text>
          </svg>

          {/* Float card: Current phase */}
          <div
            className="float-card fc-d1 absolute left-0 top-[60px] z-20 w-[280px] rounded-2xl border border-rule bg-paper p-4"
            style={{ boxShadow: "0 18px 50px -20px rgba(21,20,15,0.18), 0 4px 12px -4px rgba(21,20,15,0.06)" }}
          >
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-3">
              Current phase
            </p>
            <p className="mb-3.5 font-serif text-[20px] font-medium leading-[1.15]">
              Specialisation in applied&nbsp;ML
            </p>
            <div className="mb-2 flex items-baseline justify-between">
              <span className="text-[12px] text-ink-2">4 of 7 milestones</span>
              <span className="font-serif text-[16px] font-medium">
                57<span className="text-[11px] text-ink-3">%</span>
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-bg-2">
              <div className="progress-fill h-full rounded-full bg-green" />
            </div>
          </div>

          {/* Float card: This week */}
          <div
            className="float-card fc-d2 absolute bottom-[70px] right-[10px] z-20 w-[270px] rounded-2xl border border-rule bg-paper px-[18px] py-4"
            style={{ boxShadow: "0 18px 50px -20px rgba(21,20,15,0.18), 0 4px 12px -4px rgba(21,20,15,0.06)" }}
          >
            <div className="mb-1.5 flex items-baseline justify-between">
              <span className="font-serif text-[16px] font-medium">This week&apos;s focus</span>
              <span className="text-[11px] uppercase tracking-[0.05em] text-ink-3">Wk 14</span>
            </div>
            {WEEK_TASKS.map(({ done, label, time }) => (
              <div
                key={label}
                className="flex items-center justify-between border-b border-rule py-[9px] text-[13px] last:border-b-0"
              >
                <div className={`flex items-center gap-2.5 ${done ? "text-ink-3 line-through decoration-rule-strong" : "text-ink-2"}`}>
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] ${
                      done ? "bg-green text-white" : "border-[1.5px] border-rule-strong bg-bg-2"
                    }`}
                  >
                    {done && <Check />}
                  </span>
                  {label}
                </div>
                <span className="shrink-0 pl-2 text-[11px] tabular-nums text-ink-3">{time}</span>
              </div>
            ))}
          </div>

          {/* Float card: Market pulse */}
          <div
            className="float-card fc-d3 absolute right-[-10px] top-[280px] z-20 w-[220px] rounded-2xl border border-rule bg-paper p-4"
            style={{ boxShadow: "0 18px 50px -20px rgba(21,20,15,0.18), 0 4px 12px -4px rgba(21,20,15,0.06)" }}
          >
            <div className="mb-3 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.08em] text-terra">
              <span className="live-dot h-1.5 w-1.5 rounded-full bg-terra" />
              Live market pulse
            </div>
            {MARKET_SKILLS.map(({ name, change }) => (
              <div key={name} className="mb-2.5 flex items-baseline justify-between last:mb-0">
                <span className="text-[13px] font-medium text-ink">{name}</span>
                <span className="text-[11px] font-medium tabular-nums text-green">{change}</span>
              </div>
            ))}
          </div>

        </div>{/* end hero-visual */}
      </section>

      {/* ── Trust bar / marquee ───────────────────────────────────────── */}
      <div
        className="relative mt-14 overflow-hidden border-y border-rule py-6"
        aria-label="As featured in"
      >
        {/* Fade edges */}
        <div
          className="pointer-events-none absolute inset-y-0 left-0 z-10 w-20"
          style={{ background: "linear-gradient(to right, #F7F2E8, transparent)" }}
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute inset-y-0 right-0 z-10 w-20"
          style={{ background: "linear-gradient(to left, #F7F2E8, transparent)" }}
          aria-hidden="true"
        />

        <div className="marquee-track flex w-max items-center gap-20">
          {/* Doubled for seamless loop */}
          {[...TRUST_NAMES, ...TRUST_NAMES].map((name, i) => (
            <span
              key={`${name}-${i}`}
              className="cursor-default whitespace-nowrap font-serif text-[22px] font-normal italic text-ink-2 opacity-55 transition-opacity duration-200 hover:opacity-100"
            >
              {name}
            </span>
          ))}
        </div>
      </div>
    </>
  );
}