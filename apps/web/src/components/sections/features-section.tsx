"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Feature {
  marker:      string;
  tag:         string;
  heading:     { before?: string; em: string; after?: string };
  description: string;
  link:        { label: string; href: string };
  delay:       string;
}

// ─── Data ─────────────────────────────────────────────────────────────────────
const FEATURES: Feature[] = [
  {
    marker:      "№ 14.1",
    tag:         "Career Twin",
    heading:     { before: "An ", em: "AI persona", after: " that grows with you." },
    description: "A persistent companion that knows your plan, energy patterns and language. Voice-first conversations on commutes. Socratic questions before big decisions.",
    link:        { label: "Meet the Twin →", href: "#" },
    delay:       "0.1s",
  },
  {
    marker:      "№ 14.2",
    tag:         "Adaptive Skill Graph",
    heading:     { before: "A living ", em: "map of you", after: " and where you can go next." },
    description: "Visualise current skills, target skills, prerequisites and adjacent roles. Updates as you ship projects, take courses, or shift direction.",
    link:        { label: "See the graph →", href: "#" },
    delay:       "0.2s",
  },
  {
    marker:      "№ 14.3",
    tag:         "What-If Simulator",
    heading:     { em: "Test major decisions", after: " before you commit." },
    description: "Switch from data engineer to ML researcher? Move to Berlin? Take a sabbatical? Compare side-by-side: roadmap, salary, lifestyle, probability.",
    link:        { label: "Run a scenario →", href: "#" },
    delay:       "0.3s",
  },
  {
    marker:      "№ 14.4",
    tag:         "Live Job Market Pulse",
    heading:     { before: "The ", em: "real-time", after: " story of your target market." },
    description: "Open positions, week-over-week change, median compensation, fastest-growing skills, time-to-hire. MCP-driven aggregation across major job boards.",
    link:        { label: "View the pulse →", href: "#" },
    delay:       "0.1s",
  },
  {
    marker:      "№ 14.6",
    tag:         "Mock Interview Studio",
    heading:     { em: "Rehearse", after: " with role-specific drills." },
    description: "Behavioural, system-design, technical-coding and case-study formats. Annotated transcripts, structured feedback, and an interview-readiness score over time.",
    link:        { label: "Start a session →", href: "#" },
    delay:       "0.2s",
  },
  {
    marker:      "№ 14.10",
    tag:         "Career Health Score",
    heading:     { before: "One number. ", em: "Five honest signals." },
    description: "Roadmap progress, skill readiness, portfolio strength, market alignment, application readiness. Glanceable, transparent, never gameable.",
    link:        { label: "See methodology →", href: "#" },
    delay:       "0.3s",
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export function FeaturesSection() {
  const sectionRef = useRef<HTMLElement>(null);

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
          transition:
            opacity 0.7s cubic-bezier(.2,.7,.2,1),
            transform 0.7s cubic-bezier(.2,.7,.2,1);
        }
        .reveal.visible { opacity: 1; transform: translateY(0); }

        /* Section: terra gradient hairline at very top */
        .features-section-wrap {
          position: relative;
          overflow: hidden;
        }
        .features-section-wrap::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0;
          height: 1px;
          background: linear-gradient(90deg, transparent, #C95A3D 50%, transparent);
          opacity: 0.4;
          z-index: 1;
        }

        /* Feature card: top colour strip (expands on hover) */
        .feature-card {
          position: relative;
          overflow: hidden;
          transition: background 0.3s ease;
          cursor: default;
        }
        .feature-card::before {
          content: '';
          position: absolute;
          top: 0; left: 0;
          height: 3px; width: 0;
          transition: width 0.4s cubic-bezier(.2,.7,.2,1);
        }
        /* Per-position strip colour: 3n+1 green, 3n+2 terra, 3n+3 gold */
        .feature-card:nth-child(3n+1)::before { background: #134E3A; }
        .feature-card:nth-child(3n+2)::before { background: #C95A3D; }
        .feature-card:nth-child(3n+3)::before { background: #B68A2E; }

        /* Radial glow overlay on hover */
        .feature-card::after {
          content: '';
          position: absolute;
          inset: 0;
          background: radial-gradient(
            ellipse at 100% 0%,
            rgba(201,90,61,0.04) 0%,
            transparent 50%
          );
          opacity: 0;
          transition: opacity 0.3s ease;
          pointer-events: none;
        }
        .feature-card:hover { background: #F7F2E8; }
        .feature-card:hover::before { width: 100%; }
        .feature-card:hover::after  { opacity: 1; }

        /* Arrow link gap widens on card hover */
        .feature-card:hover .feat-arrow-link { gap: 10px; }

        /* Responsive features grid */
        .features-grid {
          display: grid;
          grid-template-columns: repeat(1, 1fr);
          max-width: 1280px;
          margin: 0 auto;
          border-top:  1px solid #C9BFA7;
          border-left: 1px solid #C9BFA7;
        }
        @media (min-width: 640px)  { .features-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (min-width: 1024px) { .features-grid { grid-template-columns: repeat(3, 1fr); } }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="features-heading"
        className="features-section-wrap border-y border-rule bg-paper px-6 py-20 sm:px-10 sm:py-[120px] lg:px-12"
      >
        {/* ── Section header ────────────────────────────────────────── */}
        <div className="mx-auto mb-[72px] max-w-[880px] text-center">

          {/* Eyebrow */}
          <p className="reveal mb-5 inline-block text-[12px] font-semibold uppercase tracking-[0.14em] text-terra">
            <em className="mr-2 font-serif text-[14px] font-medium not-italic">
              III.
            </em>
            Standout features
          </p>

          {/* Title — em uses opsz 144 axis for display optical size */}
          <h2
            id="features-heading"
            className="reveal mb-6 font-serif font-[350] leading-[1.02] tracking-[-0.025em] text-ink"
            style={{ fontSize: "clamp(32px, 4.5vw, 56px)", transitionDelay: "0.1s" }}
          >
            A career operating system,{" "}
            <em
              className="italic text-green"
              style={{ fontVariationSettings: '"opsz" 144' }}
            >
              not a chat box.
            </em>
          </h2>

          {/* Sub */}
          <p
            className="reveal mx-auto max-w-[660px] text-[18px] leading-[1.55] text-ink-2"
            style={{ transitionDelay: "0.2s" }}
          >
            Twenty-one distinctive features. These are the six users tell us
            they couldn&apos;t live without.
          </p>
        </div>

        {/* ── Features grid ─────────────────────────────────────────── */}
        <div className="features-grid">
          {FEATURES.map(({ marker, tag, heading, description, link, delay }) => (
            <article
              key={marker}
              className="feature-card reveal flex min-h-[280px] flex-col border-b border-r border-rule-strong bg-paper px-8 pb-9 pt-10"
              style={{ transitionDelay: delay }}
            >
              {/* Feature tag */}
              <p className="mb-[22px] inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-terra">
                <em className="font-serif text-[14px] font-normal not-italic normal-case tracking-normal text-ink-3">
                  {marker}
                </em>
                {tag}
              </p>

              {/* Heading with italic em in green */}
              <h4
                className="mb-[14px] font-serif text-[26px] leading-[1.1] tracking-[-0.018em] text-ink"
                style={{ fontWeight: 400 }}
              >
                {heading.before}
                <em
                  className="italic text-green"
                  style={{ fontVariationSettings: '"opsz" 144' }}
                >
                  {heading.em}
                </em>
                {heading.after}
              </h4>

              {/* Description — pushed to bottom */}
              <p className="mt-auto text-[14px] leading-[1.6] text-ink-2">
                {description}
              </p>

              {/* Arrow link */}
              <Link
                href={link.href}
                className="feat-arrow-link mt-[18px] inline-flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-terra transition-[gap] duration-200"
              >
                {link.label}
              </Link>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}