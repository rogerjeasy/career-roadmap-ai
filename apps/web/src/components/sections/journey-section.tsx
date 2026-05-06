"use client";

import { useEffect, useRef } from "react";

// ─── Step data ────────────────────────────────────────────────────────────────
interface Step {
  num:         string;
  title:       string;
  description: string;
  isLast:      boolean;
}

const STEPS: Step[] = [
  {
    num:         "01",
    title:       "Upload your CV",
    description: "Drop in a CV, resume, LinkedIn export, GitHub or portfolio URL. We parse a structured profile of your skills, experience, projects and signals of impact.",
    isLast:      false,
  },
  {
    num:         "02",
    title:       "Set your direction",
    description: "Pick a target role, paste a job posting, or let the AI suggest careers that fit your strengths, geography, salary range and life constraints.",
    isLast:      false,
  },
  {
    num:         "03",
    title:       "Get your roadmap",
    description: "The AI generates a personalised, multi-phase plan with milestones, weekly routines, learning resources, projects and networking actions — fully editable.",
    isLast:      false,
  },
  {
    num:         "04",
    title:       "Track & adapt",
    description: "Daily habits, weekly reviews, market alerts, and live opportunity radar. The roadmap adapts as you complete milestones or as the market shifts.",
    isLast:      true,
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export function JourneySection() {
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
        /* Scroll reveal — shared with other sections */
        .reveal {
          opacity: 0;
          transform: translateY(22px);
          transition:
            opacity 0.7s cubic-bezier(.2,.7,.2,1),
            transform 0.7s cubic-bezier(.2,.7,.2,1);
        }
        .reveal.visible {
          opacity: 1;
          transform: translateY(0);
        }

        /* Step connector arrow sitting on the right border */
        .step-connector {
          position: absolute;
          top: 69px;
          right: -12px;
          width: 24px;
          height: 24px;
          background: var(--color-bg);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1;
          font-size: 12px;
          color: var(--color-terra);
        }

        /* On 2-col mobile layout, hide connector on even-indexed steps
           (they sit on the right column edge with no step to the right) */
        @media (max-width: 1023px) {
          .step-even .step-connector { display: none; }
        }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="journey-heading"
        className="bg-bg px-6 py-20 sm:px-10 sm:py-[120px] lg:px-12"
      >
        {/* ── Section header ────────────────────────────────────────── */}
        <div className="mx-auto mb-[72px] max-w-[880px] text-center">

          {/* Eyebrow */}
          <p className="reveal mb-5 inline-block text-[12px] font-semibold uppercase tracking-[0.14em] text-terra">
            <em className="mr-2 font-serif text-[14px] font-medium not-italic">
              II.
            </em>
            The journey
          </p>

          {/* Title */}
          <h2
            id="journey-heading"
            className="reveal mb-6 font-serif font-[350] leading-[1.02] tracking-[-0.025em] text-ink"
            style={{ fontSize: "clamp(32px, 4.5vw, 56px)", transitionDelay: "0.1s" }}
          >
            From CV to career plan, in{" "}
            <em className="italic text-green">under fifteen minutes.</em>
          </h2>

          {/* Sub */}
          <p
            className="reveal mx-auto max-w-[660px] text-[18px] leading-[1.55] text-ink-2"
            style={{ transitionDelay: "0.2s" }}
          >
            A step-by-step onboarding so you always know what&apos;s being
            asked, and what you&apos;ll get in return.
          </p>
        </div>

        {/* ── Steps grid ────────────────────────────────────────────── */}
        <div
          className="mx-auto max-w-[1280px] border-t border-rule"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(1, 1fr)",
          }}
        >
          <style>{`
            .how-grid { grid-template-columns: repeat(1, 1fr); }
            @media (min-width: 640px)  { .how-grid { grid-template-columns: repeat(2, 1fr); } }
            @media (min-width: 1024px) { .how-grid { grid-template-columns: repeat(4, 1fr); } }
          `}</style>

          <div className="how-grid" style={{ display: "grid" }}>
            {STEPS.map(({ num, title, description, isLast }, idx) => (
              <div
                key={num}
                className={[
                  "reveal relative pb-7 pl-8 pr-8 pt-10",
                  !isLast && "border-b border-rule lg:border-b-0 lg:border-r lg:border-rule",
                  // even steps (0-indexed): 02 and 04 sit on right col at sm breakpoint
                  idx % 2 === 1 ? "step-even" : "",
                ].filter(Boolean).join(" ")}
                style={{ transitionDelay: `${(idx + 1) * 0.1}s` }}
              >
                {/* Arrow connector — hidden on last step */}
                {!isLast && (
                  <div className="step-connector" aria-hidden="true">→</div>
                )}

                {/* Step number */}
                <p
                  className="mb-7 font-serif italic text-terra"
                  style={{ fontSize: 64, fontWeight: 350, lineHeight: 1 }}
                >
                  {num}
                </p>

                {/* Step title */}
                <h4
                  className="mb-3 font-serif text-[20px] leading-[1.2] tracking-[-0.01em] text-ink"
                  style={{ fontWeight: 450 }}
                >
                  {title}
                </h4>

                {/* Step description */}
                <p className="text-[14px] leading-[1.55] text-ink-2">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}