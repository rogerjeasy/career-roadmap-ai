"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Pillar {
  num:         string;
  icon:        ReactNode;
  title:       string;
  description: string;
  delay:       string;
}

// ─── SVG icons ────────────────────────────────────────────────────────────────
const ICON_PROPS = {
  viewBox:      "0 0 32 32",
  fill:         "none",
  stroke:       "currentColor",
  strokeWidth:  1.4,
  "aria-hidden": true,
  className:    "w-9 h-9 mb-7 text-green shrink-0",
} as const;

function IconCareerDesign() {
  return (
    <svg {...ICON_PROPS}>
      <circle cx="16" cy="11" r="5" />
      <path d="M16 16v6m-4 0h8m-12 6c0-3 4-5 8-5s8 2 8 5" />
      <circle cx="24" cy="6" r="2" fill="currentColor" />
    </svg>
  );
}

function IconMarketIntel() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M4 24l6-8 5 4 7-10 6 6" />
      <circle cx="4"  cy="24" r="1.5" fill="currentColor" />
      <circle cx="10" cy="16" r="1.5" fill="currentColor" />
      <circle cx="15" cy="20" r="1.5" fill="currentColor" />
      <circle cx="22" cy="10" r="1.5" fill="currentColor" />
      <circle cx="28" cy="16" r="1.5" fill="currentColor" />
    </svg>
  );
}

function IconGapAnalysis() {
  return (
    <svg {...ICON_PROPS}>
      <rect x="6" y="4" width="20" height="24" rx="2" />
      <path d="M11 11h10M11 16h10M11 21h6" />
      <circle cx="24" cy="22" r="4" />
      <path d="M27 25l3 3" strokeLinecap="round" />
    </svg>
  );
}

function IconExecution() {
  return (
    <svg {...ICON_PROPS}>
      <rect x="4" y="6" width="24" height="22" rx="2" />
      <path d="M4 12h24M9 4v4M23 4v4" />
      <rect x="9"  y="16" width="3" height="3" fill="currentColor" />
      <rect x="14" y="16" width="3" height="3" fill="currentColor" />
      <rect x="19" y="16" width="3" height="3" fill="currentColor" />
      <rect x="9"  y="21" width="3" height="3" fill="currentColor" />
      <rect x="14" y="21" width="3" height="3" fill="currentColor" opacity={0.4} />
    </svg>
  );
}

function IconAdaptation() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M16 4 A12 12 0 1 1 4 16" />
      <path d="M4 16l3-3M4 16l3 3" strokeLinecap="round" />
      <path d="M22 12l-6 6-3-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ─── Data ─────────────────────────────────────────────────────────────────────
const PILLARS: Pillar[] = [
  {
    num:         "01",
    icon:        <IconCareerDesign />,
    title:       "AI-Guided Career Design",
    description: "A guided conversation with an LLM career coach turns your situation, goals and constraints into a multi-phase, fully editable roadmap.",
    delay:       "0.10s",
  },
  {
    num:         "02",
    icon:        <IconMarketIntel />,
    title:       "Real-Time Market Intelligence",
    description: "Live signals from job boards, GitHub, LinkedIn and industry communities — filtered to what actually matters for your plan this week.",
    delay:       "0.20s",
  },
  {
    num:         "03",
    icon:        <IconGapAnalysis />,
    title:       "CV-Based Gap Analysis",
    description: "Upload a CV and a target role. We parse both, surface the gaps, and convert each one into a concrete project, course or networking action.",
    delay:       "0.30s",
  },
  {
    num:         "04",
    icon:        <IconExecution />,
    title:       "Plan Execution & Tracking",
    description: "Weekly time-budget, daily habits with streaks, a Friday review ritual, and quantified progress that turns ambition into measurable execution.",
    delay:       "0.40s",
  },
  {
    num:         "05",
    icon:        <IconAdaptation />,
    title:       "Continuous Adaptation",
    description: "Your plan updates when you finish a milestone, change direction, or when the market shifts. A five-minute chat is enough — no more redrafting.",
    delay:       "0.50s",
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export function PillarsSection() {
  const sectionRef = useRef<HTMLElement>(null);

  // Scroll-triggered reveal — mirrors the original IntersectionObserver logic
  useEffect(() => {
    const els = sectionRef.current?.querySelectorAll<HTMLElement>(".reveal");
    if (!els?.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );

    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <style>{`
        /* Scroll reveal */
        .reveal {
          opacity: 0;
          transform: translateY(22px);
          transition: opacity 0.7s cubic-bezier(.2,.7,.2,1),
                      transform 0.7s cubic-bezier(.2,.7,.2,1);
        }
        .reveal.visible {
          opacity: 1;
          transform: translateY(0);
        }

        /* Pillar hover lift */
        .pillar-card {
          transition: background 0.25s ease;
        }
        .pillar-card:hover {
          background: #FFFFFF;
        }

        /* Underline sweep on pillar title hover */
        .pillar-title {
          position: relative;
          display: inline;
        }
        .pillar-card:hover .pillar-title {
          color: #134E3A;
        }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="pillars-heading"
        className="border-y border-rule bg-bg-2 px-5 py-20 sm:px-10 sm:py-24 lg:px-12 lg:py-[120px]"
      >
        {/* ── Section header ──────────────────────────────────────────── */}
        <div className="mx-auto mb-16 max-w-[880px] text-center lg:mb-[72px]">

          {/* Eyebrow */}
          <p className="reveal mb-5 inline-block text-[12px] font-semibold uppercase tracking-[0.14em] text-terra">
            <em className="font-serif font-medium not-italic mr-2 text-[14px]">I.</em>
            The architecture of a career
          </p>

          {/* Heading */}
          <h2
            id="pillars-heading"
            className="reveal mb-6 font-serif font-[350] leading-[1.02] tracking-[-0.025em] text-ink"
            style={{
              fontSize: "clamp(32px, 5vw, 56px)",
              transitionDelay: "0.1s",
            }}
          >
            Five{" "}
            <em className="italic text-green">pillars.</em>{" "}
            One coherent system for the long arc of your career.
          </h2>

          {/* Sub */}
          <p
            className="reveal mx-auto max-w-[660px] text-[16px] leading-[1.55] text-ink-2 sm:text-[18px]"
            style={{ transitionDelay: "0.2s" }}
          >
            Most career tools solve one slice — a CV, a course, a job board, a
            chat. We tied them all to a single living plan that adapts as you
            grow and as the market moves.
          </p>
        </div>

        {/* ── Pillars grid ─────────────────────────────────────────────── */}
        {/*
          Border pattern from the original:
          - border-top + border-left on the grid container
          - border-right + border-bottom on each cell
          This draws the full grid lines.
        */}
        {/* Responsive columns via media queries — avoids Tailwind purge with dynamic grid counts */}
        <style>{`
          .pillars-grid {
            display: grid;
            grid-template-columns: repeat(1, 1fr);
            max-width: 1280px;
            margin: 0 auto;
            border-top: 1px solid #C9BFA7;
            border-left: 1px solid #C9BFA7;
          }
          @media (min-width: 640px)  { .pillars-grid { grid-template-columns: repeat(2, 1fr); } }
          @media (min-width: 1280px) { .pillars-grid { grid-template-columns: repeat(5, 1fr); } }
        `}</style>

        <div className="pillars-grid">
            {PILLARS.map(({ num, icon, title, description, delay }) => (
              <article
                key={num}
                className="pillar-card reveal flex min-h-[320px] cursor-default flex-col border-b border-r border-rule-strong bg-bg px-7 pb-10 pt-9"
                style={{ transitionDelay: delay }}
              >
                {/* Number */}
                <p className="mb-6 font-serif text-[22px] font-normal italic text-terra">
                  {num}
                </p>

                {/* Icon */}
                {icon}

                {/* Title */}
                <h3 className="mb-3.5 font-serif text-[22px] font-[450] leading-[1.15] tracking-[-0.01em] text-ink transition-colors duration-200">
                  <span className="pillar-title">{title}</span>
                </h3>

                {/* Description — pushed to bottom with mt-auto */}
                <p className="mt-auto text-[13.5px] leading-[1.55] text-ink-2">
                  {description}
                </p>
              </article>
            ))}
        </div>
      </section>
    </>
  );
}