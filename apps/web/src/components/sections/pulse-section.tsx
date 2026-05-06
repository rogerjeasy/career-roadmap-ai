"use client";

import { useEffect, useRef } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface TickerItem  { role: string; city: string; change: string; up: boolean }
interface TrendRole   { name: string; meta: string; pct: string; hot: boolean; openings: string; bar: number }
interface SkillChip   { label: string; delta: string; type: "flame" | "rising" | "steady"; delay: string }
interface SalaryRow   { role: string; city: string; points: string; amt: string; delta: string }
interface NewsItem    { when: string; title: string; tag: string; tagType: "green" | "terra" | "gold"; source: string; isNew: boolean }

// ─── Data ────────────────────────────────────────────────────────────────────
const TICKER: TickerItem[] = [
  { role: "ML Engineer",           city: "Berlin",    change: "+38%", up: true  },
  { role: "Forward Deployed Eng",  city: "SF",        change: "+62%", up: true  },
  { role: "AI Product Manager",    city: "London",    change: "+27%", up: true  },
  { role: "Data Eng · Remote",     city: "Global",    change: "+14%", up: true  },
  { role: "DevRel · Open Source",  city: "EU",        change: "+19%", up: true  },
  { role: "Solutions Architect",   city: "Singapore", change: "+22%", up: true  },
  { role: "Front-end Eng",         city: "Lisbon",    change: "−4%",  up: false },
  { role: "Eval Researcher",       city: "NYC",       change: "+44%", up: true  },
  { role: "Platform Eng",          city: "Zurich",    change: "+11%", up: true  },
  { role: "Growth PM",             city: "Toronto",   change: "+8%",  up: true  },
];

const TREND_ROLES: TrendRole[] = [
  { name: "AI / ML Engineer",          meta: "Software · Senior · Global",       pct: "+38%", hot: true,  openings: "8,412 open",  bar: 92 },
  { name: "Forward Deployed Engineer", meta: "AI Labs · Mid–Senior · US, EU",    pct: "+62%", hot: true,  openings: "1,194 open",  bar: 78 },
  { name: "AI Product Manager",        meta: "Tech · Mid · Remote-first",        pct: "+27%", hot: false, openings: "3,028 open",  bar: 64 },
  { name: "Data Engineer",             meta: "Cloud · Mid–Senior · Global",      pct: "+14%", hot: false, openings: "12,860 open", bar: 48 },
  { name: "DevRel · Open-source",      meta: "Developer Tools · EU, US",         pct: "+19%", hot: false, openings: "682 open",    bar: 38 },
];

const HOT_SKILLS: SkillChip[] = [
  { label: "RAG systems",  delta: "+86%",  type: "flame",  delay: "0.05s" },
  { label: "LLM evals",   delta: "+71%",  type: "flame",  delay: "0.10s" },
  { label: "Agent design", delta: "+64%",  type: "flame",  delay: "0.15s" },
  { label: "PyTorch · prod",delta: "+38%", type: "rising", delay: "0.20s" },
  { label: "Vector DBs",   delta: "+31%",  type: "rising", delay: "0.25s" },
  { label: "MCP servers",  delta: "+118%", type: "rising", delay: "0.30s" },
];

const STEADY_SKILLS: SkillChip[] = [
  { label: "TypeScript",    delta: "+9%",  type: "steady", delay: "0.35s" },
  { label: "Kubernetes",    delta: "+6%",  type: "steady", delay: "0.40s" },
  { label: "Postgres",      delta: "+4%",  type: "steady", delay: "0.45s" },
  { label: "FastAPI",       delta: "+11%", type: "steady", delay: "0.50s" },
  { label: "System design", delta: "+12%", type: "steady", delay: "0.55s" },
  { label: "Rust",          delta: "+18%", type: "steady", delay: "0.60s" },
];

const SALARY_ROWS: SalaryRow[] = [
  {
    role: "ML Engineer", city: "Berlin · EUR",
    points: "0,16 10,14 20,15 30,10 40,11 50,5 60,3",
    amt: "€92k", delta: "+11.4%",
  },
  {
    role: "AI Product Mgr", city: "London · GBP",
    points: "0,12 10,14 20,11 30,8 40,9 50,6 60,7",
    amt: "£86k", delta: "+7.2%",
  },
];

const NEWS: NewsItem[] = [
  {
    when: "2 min",
    title: "Major AI lab opens 40+ engineering roles across SF & London — RAG & eval focus",
    tag: "Hiring", tagType: "terra", source: "Tech industry · 4 sources", isNew: true,
  },
  {
    when: "14 min",
    title: `"MCP-native" engineer is the fastest-growing job title on LinkedIn this quarter`,
    tag: "Trends", tagType: "green", source: "LinkedIn · Greenhouse", isNew: true,
  },
  {
    when: "42 min",
    title: "Median ML engineer compensation in Switzerland up 14% YoY, surpassing US-remote band",
    tag: "Salary", tagType: "gold", source: "Levels.fyi · ETHZ jobs", isNew: false,
  },
  {
    when: "1 h",
    title: "Anthropic, Mistral & xAI added to top-10 most-applied-to AI startups (EU)",
    tag: "Hiring", tagType: "terra", source: "Otta · Welcome to the Jungle", isNew: false,
  },
  {
    when: "2 h",
    title: "Open-source RAG project lands $5M seed; first-time contributors welcomed",
    tag: "Open-source", tagType: "green", source: "GitHub Trending", isNew: false,
  },
  {
    when: "3 h",
    title: "Remote-friendly senior IC roles up 28% in EU. Berlin and Lisbon lead the chart.",
    tag: "Geo", tagType: "gold", source: "Indeed · Honeypot", isNew: false,
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export function PulseSection() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = sectionRef.current;
    if (!root) return;

    // Scroll reveal
    const revealEls = root.querySelectorAll<HTMLElement>(".reveal");
    const revealIO = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { e.target.classList.add("visible"); revealIO.unobserve(e.target); }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => revealIO.observe(el));

    // Bar fill — triggered when each row enters viewport
    const barRows = root.querySelectorAll<HTMLElement>(".anim-bar");
    const barIO = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { e.target.classList.add("in-view"); barIO.unobserve(e.target); }
        });
      },
      { threshold: 0.3 }
    );
    barRows.forEach((el) => barIO.observe(el));

    return () => { revealIO.disconnect(); barIO.disconnect(); };
  }, []);

  return (
    <>
      <style>{`
        /* Reveal */
        .reveal { opacity:0; transform:translateY(22px); transition: opacity .7s cubic-bezier(.2,.7,.2,1), transform .7s cubic-bezier(.2,.7,.2,1); }
        .reveal.visible { opacity:1; transform:translateY(0); }

        /* Live dot ripple */
        @keyframes livepulse {
          0%   { box-shadow: 0 0 0 0 rgba(201,90,61,0.7); }
          70%  { box-shadow: 0 0 0 10px rgba(201,90,61,0); }
          100% { box-shadow: 0 0 0 0 rgba(201,90,61,0); }
        }
        .live-dot-anim { animation: livepulse 1.8s infinite; }

        /* Ticker scroll */
        @keyframes scrolltape {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        .ticker-tape { animation: scrolltape 50s linear infinite; }
        .ticker-wrap:hover .ticker-tape { animation-play-state: paused; }

        /* Ticker edge fades */
        .ticker-wrap { position: relative; }
        .ticker-wrap::before,
        .ticker-wrap::after {
          content: ''; position: absolute; top: 0; bottom: 0; width: 80px; z-index: 2; pointer-events: none;
        }
        .ticker-wrap::before { left:  0; background: linear-gradient(90deg,  #15140F, transparent); }
        .ticker-wrap::after  { right: 0; background: linear-gradient(270deg, #15140F, transparent); }

        /* Trending bars */
        .bar-fill {
          height: 100%; border-radius: 999px;
          background: #134E3A;
          width: 0;
          transition: width 1.6s cubic-bezier(.2,.7,.2,1);
        }
        .bar-fill.hot { background: #C95A3D; }
        .anim-bar.in-view .bar-fill { width: var(--bar-w, 50%); }

        /* Skill chip entrance */
        @keyframes chipin {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .skill-chip {
          opacity: 0;
          animation: chipin .5s cubic-bezier(.2,.7,.2,1) forwards;
        }
        .skill-chip:hover { transform: translateY(-1px); }

        /* NEW badge blink */
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.55; }
        }
        .news-new-badge { animation: blink 2.4s ease-in-out infinite; }

        /* Responsive overrides */
        .pulse-header-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 64px; align-items: end; }
        .pulse-data-grid   { display: grid; grid-template-columns: 1.15fr 1fr 0.95fr; gap: 24px; }
        @media (max-width: 1023px) {
          .pulse-header-grid { grid-template-columns: 1fr; gap: 24px; }
          .pulse-data-grid   { grid-template-columns: 1fr; }
          .pulse-meta-right  { text-align: left !important; }
        }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="pulse-heading"
        className="border-y border-rule bg-bg-2 overflow-hidden relative"
        style={{ padding: "110px 0 120px" }}
      >

        {/* ── Section header ────────────────────────────────────────── */}
        <div className="pulse-header-grid mx-auto mb-12 max-w-[1280px] px-6 sm:px-12">

          {/* Left: badge + title */}
          <div>
            {/* Live badge */}
            <div className="reveal mb-[22px] inline-flex items-center gap-2.5 rounded-full bg-ink px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-bg">
              <span
                className="live-dot-anim h-2 w-2 shrink-0 rounded-full bg-terra"
                aria-hidden="true"
              />
              Live · Career Pulse
            </div>

            {/* Title */}
            <h2
              id="pulse-heading"
              className="reveal font-serif font-[350] leading-[1.02] tracking-[-0.025em] text-ink"
              style={{ fontSize: "clamp(32px, 4vw, 56px)", transitionDelay: "0.1s" }}
            >
              What&apos;s{" "}
              <em className="italic text-green">moving</em>{" "}
              in the career market — right now.
            </h2>
          </div>

          {/* Right: meta */}
          <div
            className="reveal pulse-meta-right text-[13px] leading-[1.55] text-ink-2"
            style={{ textAlign: "right", paddingBottom: 6, transitionDelay: "0.2s" }}
          >
            <span className="mb-1 block font-serif text-[14px] italic text-terra">
              Last update · 12 sec. ago
            </span>
            Aggregated from 142,000+ live job postings, GitHub trending, LinkedIn
            signals, and 38 industry feeds via MCP.
          </div>
        </div>

        {/* ── Ticker tape ───────────────────────────────────────────── */}
        <div
          className="ticker-wrap reveal mb-9 overflow-hidden border-y bg-ink"
          style={{ borderColor: "#C9BFA7" }}
        >
          <div
            className="ticker-tape flex"
            style={{ whiteSpace: "nowrap", width: "max-content" }}
          >
            {[...TICKER, ...TICKER].map((item, i) => (
              <div
                key={i}
                className="inline-flex items-center gap-3 border-r px-7 py-[14px] text-[13px]"
                style={{ borderColor: "rgba(247,242,232,0.10)" }}
              >
                <span className="font-medium text-bg">{item.role}</span>
                <span className="font-serif text-[13px] italic" style={{ color: "rgba(247,242,232,0.55)" }}>
                  {item.city}
                </span>
                <span
                  className="text-[12.5px] font-semibold tabular-nums"
                  style={{ color: item.up ? "#7ED2A4" : "#E89A85" }}
                >
                  {item.up ? "▲ " : "▼ "}{item.change}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Three-column data grid ────────────────────────────────── */}
        <div className="pulse-data-grid mx-auto max-w-[1280px] px-6 sm:px-12">

          {/* ── LEFT: Trending roles ───────────────────────── */}
          <div
            className="reveal flex flex-col rounded-[10px] border border-rule bg-bg p-7"
            style={{ minHeight: 440 }}
          >
            <div className="mb-5 flex items-baseline justify-between border-b border-rule pb-3.5">
              <h3 className="font-serif text-[20px] font-medium tracking-[-0.01em] text-ink">
                Trending roles · 7-day
              </h3>
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-3">
                Top 5 by demand growth
              </span>
            </div>

            {TREND_ROLES.map((r) => (
              <div
                key={r.name}
                className="anim-bar role-row grid items-center gap-x-3.5 gap-y-0 border-b border-dashed border-rule py-3.5 last:border-b-0"
                style={
                  {
                    gridTemplateColumns: "1fr auto",
                    "--bar-w": `${r.bar}%`,
                  } as React.CSSProperties
                }
              >
                {/* Info */}
                <div className="flex flex-col gap-1">
                  <span className="font-serif text-[16px] font-medium tracking-[-0.005em] text-ink">
                    {r.name}
                  </span>
                  <span className="text-[11.5px] tracking-[0.02em] text-ink-3">
                    {r.meta.split(" · ").map((part, i, arr) => (
                      <span key={part}>
                        {part}
                        {i < arr.length - 1 && (
                          <span className="mx-1.5 opacity-50">·</span>
                        )}
                      </span>
                    ))}
                  </span>
                </div>

                {/* Stat */}
                <div className="text-right">
                  <div
                    className="text-[13px] font-semibold tabular-nums"
                    style={{ color: r.hot ? "#AC4A30" : "#134E3A" }}
                  >
                    {r.pct}
                  </div>
                  <div className="mt-0.5 text-[10.5px] tracking-[0.02em] text-ink-3">
                    {r.openings}
                  </div>
                </div>

                {/* Bar — spans full width */}
                <div className="col-span-2 mt-0.5 h-1 overflow-hidden rounded-full bg-bg-2">
                  <div className={`bar-fill${r.hot ? " hot" : ""}`} />
                </div>
              </div>
            ))}
          </div>

          {/* ── MIDDLE: Skills + Salary ────────────────────── */}
          <div
            className="reveal flex flex-col rounded-[10px] border border-rule bg-bg p-7"
            style={{ minHeight: 440, transitionDelay: "0.1s" }}
          >
            <div className="mb-5 flex items-baseline justify-between border-b border-rule pb-3.5">
              <h3 className="font-serif text-[20px] font-medium tracking-[-0.01em] text-ink">
                Skills in demand
              </h3>
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-3">
                This week
              </span>
            </div>

            {/* Hot + Rising */}
            <Divider>Hot · trending up</Divider>
            <div className="mb-5 flex flex-wrap gap-2">
              {HOT_SKILLS.map((s) => (
                <SkillBadge key={s.label} skill={s} />
              ))}
            </div>

            {/* Steady */}
            <Divider>Steady · core demand</Divider>
            <div className="mb-5 flex flex-wrap gap-2">
              {STEADY_SKILLS.map((s) => (
                <SkillBadge key={s.label} skill={s} />
              ))}
            </div>

            {/* Salary */}
            <Divider>Salary deltas · mid-senior</Divider>
            {SALARY_ROWS.map((row) => (
              <div
                key={row.role}
                className="flex items-center justify-between border-b border-dashed border-rule py-2.5 last:border-b-0"
              >
                <div>
                  <div className="text-[13px] font-medium text-ink">{row.role}</div>
                  <div className="text-[10.5px] tracking-[0.04em] text-ink-3">{row.city}</div>
                </div>
                <svg viewBox="0 0 60 22" fill="none" className="h-[22px] w-[60px]" aria-hidden="true">
                  <polyline
                    points={row.points}
                    stroke="#134E3A"
                    strokeWidth="1.5"
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <div className="text-right">
                  <div className="font-serif text-[14px] font-medium tabular-nums text-ink">{row.amt}</div>
                  <div className="text-[10.5px] font-semibold tabular-nums text-green">{row.delta}</div>
                </div>
              </div>
            ))}
          </div>

          {/* ── RIGHT: News feed ───────────────────────────── */}
          <div
            className="reveal flex flex-col rounded-[10px] border border-rule bg-bg p-7"
            style={{ minHeight: 440, transitionDelay: "0.2s" }}
          >
            <div className="mb-5 flex items-baseline justify-between border-b border-rule pb-3.5">
              <h3 className="font-serif text-[20px] font-medium tracking-[-0.01em] text-ink">
                What&apos;s making news
              </h3>
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-3">
                Live feed
              </span>
            </div>

            <div className="flex flex-1 flex-col">
              {NEWS.map((item) => (
                <div
                  key={item.when + item.title.slice(0, 20)}
                  className="relative flex gap-3.5 border-b border-dashed border-rule py-3.5 last:border-b-0"
                >
                  {/* Time */}
                  <div
                    className="w-[50px] shrink-0 pt-0.5 font-serif text-[11.5px] italic text-terra"
                  >
                    {item.when}
                  </div>

                  {/* Body */}
                  <div className="flex-1 pr-8">
                    <p className="mb-1 text-[13.5px] font-medium leading-[1.4] text-ink">
                      {item.title}
                    </p>
                    <p className="text-[11px] font-medium uppercase tracking-[0.04em] text-ink-3">
                      <NewsTag type={item.tagType}>{item.tag}</NewsTag>
                      {item.source}
                    </p>
                  </div>

                  {/* NEW badge */}
                  {item.isNew && (
                    <span
                      className="news-new-badge absolute right-0 top-3.5 rounded-[3px] bg-terra px-1.5 py-0.5 text-[9px] font-bold tracking-[0.08em] text-white"
                    >
                      NEW
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function Divider({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-[14px] flex items-center gap-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3">
      <span className="h-px flex-1 bg-rule" />
      {children}
      <span className="h-px flex-1 bg-rule" />
    </div>
  );
}

function SkillBadge({ skill }: { skill: SkillChip }) {
  const base = "skill-chip inline-flex items-center gap-1.5 rounded-[6px] border px-[11px] py-[7px] text-[12.5px] font-medium transition-all duration-200";
  const styles: Record<SkillChip["type"], string> = {
    flame:  "bg-terra border-terra text-white",
    rising: "bg-green-soft border-green text-green-2",
    steady: "bg-paper border-rule text-ink-2 hover:border-green hover:text-ink",
  };
  return (
    <span
      className={`${base} ${styles[skill.type]}`}
      style={{ animationDelay: skill.delay }}
    >
      {skill.type === "flame" && <span aria-hidden="true">🔥</span>}
      {skill.label}
      <span
        className="rounded-[3px] px-[5px] py-px text-[10.5px] font-bold"
        style={{ background: "rgba(0,0,0,0.07)" }}
      >
        {skill.delta}
      </span>
    </span>
  );
}

function NewsTag({ type, children }: { type: "green" | "terra" | "gold"; children: React.ReactNode }) {
  const styles = {
    green: "bg-green-soft text-green-2",
    terra: "bg-terra-soft text-terra-2",
    gold:  "text-gold",
  };
  const goldBg = type === "gold" ? { background: "#F4E4C5" } : {};
  return (
    <span
      className={`mr-1.5 rounded-[3px] px-[5px] py-px font-serif text-[10.5px] font-medium italic normal-case tracking-normal ${styles[type]}`}
      style={goldBg}
    >
      {children}
    </span>
  );
}