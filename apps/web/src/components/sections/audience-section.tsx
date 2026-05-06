"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface AudienceCard {
  icon:        ReactNode;
  title:       string;
  description: string;
  tone:        "green" | "terra";
  delay:       string;
}

// ─── Icon SVGs ────────────────────────────────────────────────────────────────
const SVG = (props: { children: ReactNode }) => (
  <svg
    width="20" height="20" viewBox="0 0 20 20"
    fill="none" stroke="currentColor" strokeWidth="1.5"
    aria-hidden="true"
  >
    {props.children}
  </svg>
);

// ─── Data ────────────────────────────────────────────────────────────────────
const CARDS: AudienceCard[] = [
  {
    tone:  "green",
    delay: "0.1s",
    icon: (
      <SVG>
        <path d="M2 6l8-3 8 3-8 3-8-3z" />
        <path d="M5 7.5v4c0 1.5 2.5 3 5 3s5-1.5 5-3v-4M18 7v5" />
      </SVG>
    ),
    title:       "Students & new grads",
    description: "Translate a degree into a concrete first-role plan and a competitive profile.",
  },
  {
    tone:  "terra",
    delay: "0.2s",
    icon: (
      <SVG>
        <path d="M3 17V8l7-5 7 5v9" />
        <path d="M8 17v-5h4v5" />
      </SVG>
    ),
    title:       "Active job seekers",
    description: "Target specific roles, fix CV gaps, prepare for interviews, track applications end-to-end.",
  },
  {
    tone:  "green",
    delay: "0.3s",
    icon: (
      <SVG>
        <circle cx="10" cy="10" r="7" />
        <path d="M3 10h14M10 3a10 10 0 0 1 0 14M10 3a10 10 0 0 0 0 14" />
      </SVG>
    ),
    title:       "Career switchers",
    description: "Map transferable skills, identify gaps, build a credible new identity in a new field.",
  },
  {
    tone:  "terra",
    delay: "0.1s",
    icon: (
      <SVG>
        <path d="M3 17l4-4 3 3 7-8" />
        <path d="M13 8h4v4" />
      </SVG>
    ),
    title:       "Working professionals",
    description: "Level up to senior or staff roles, pivot into adjacent fields, prepare for promotion.",
  },
  {
    tone:  "green",
    delay: "0.2s",
    icon: (
      <SVG>
        <circle cx="10" cy="6" r="3" />
        <path d="M3 17c0-3 3-5 7-5s7 2 7 5" />
        <path d="M14 4l2 2 2-2" />
      </SVG>
    ),
    title:       "Returning professionals",
    description: "Re-enter the workforce after a break with a structured ramp-up and visibility plan.",
  },
  {
    tone:  "terra",
    delay: "0.3s",
    icon: (
      <SVG>
        <path d="M2 10h4l2-5 4 10 2-5h4" />
      </SVG>
    ),
    title:       "Freelancers & creators",
    description: "Plan portfolio assets, content strategy, outreach routines and reputation milestones.",
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export function AudienceSection() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const els = sectionRef.current?.querySelectorAll<HTMLElement>(".reveal");
    if (!els?.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { e.target.classList.add("visible"); io.unobserve(e.target); }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <>
      <style>{`
        .reveal { opacity:0; transform:translateY(22px); transition: opacity .7s cubic-bezier(.2,.7,.2,1), transform .7s cubic-bezier(.2,.7,.2,1); }
        .reveal.visible { opacity:1; transform:translateY(0); }

        .audience-card {
          transition: background .25s ease, border-color .25s ease,
                      transform .25s ease, box-shadow .25s ease;
        }
        .audience-card:hover {
          background: #FFFFFF;
          border-color: #C9BFA7;
          transform: translateY(-2px);
          box-shadow: 0 8px 32px -8px rgba(21,20,15,0.1);
        }

        /* Responsive grid */
        .audience-grid-inner {
          display: grid;
          grid-template-columns: repeat(1, 1fr);
          gap: 16px;
        }
        @media (min-width: 640px)  { .audience-grid-inner { grid-template-columns: repeat(2, 1fr); } }
        @media (min-width: 1024px) { .audience-grid-inner { grid-template-columns: repeat(3, 1fr); } }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="audience-heading"
        className="border-y border-rule bg-bg-2 px-6 py-20 sm:px-10 sm:py-[120px] lg:px-12"
      >
        {/* ── Section header ────────────────────────────────────────── */}
        <div className="mx-auto mb-[72px] max-w-[880px] text-center">

          <p className="reveal mb-5 inline-block text-[12px] font-semibold uppercase tracking-[0.14em] text-terra">
            <em className="mr-2 font-serif text-[14px] font-medium not-italic">IV.</em>
            For everyone with a serious plan
          </p>

          <h2
            id="audience-heading"
            className="reveal mb-6 font-serif font-[350] leading-[1.02] tracking-[-0.025em] text-ink"
            style={{ fontSize: "clamp(32px, 4.5vw, 56px)", transitionDelay: "0.1s" }}
          >
            Whoever you are.{" "}
            <em className="italic text-green">Wherever you are.</em>
          </h2>

          <p
            className="reveal mx-auto max-w-[660px] text-[18px] leading-[1.55] text-ink-2"
            style={{ transitionDelay: "0.2s" }}
          >
            Country-aware from day one. Visa rules, salary norms, networking
            events and hiring rhythms differ across markets — we treat that as
            first-class data, not an afterthought.
          </p>
        </div>

        {/* ── Audience cards grid ───────────────────────────────────── */}
        <div className="audience-grid-inner mx-auto max-w-[1280px]">
          {CARDS.map(({ icon, title, description, tone, delay }) => (
            <article
              key={title}
              className="audience-card reveal flex gap-[18px] rounded-[6px] border border-rule bg-bg p-7"
              style={{ transitionDelay: delay }}
            >
              {/* Icon container */}
              <div
                className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[8px]"
                style={{
                  background: tone === "green" ? "#DCE7DC" : "#F4DDD2",
                  color:      tone === "green" ? "#134E3A" : "#AC4A30",
                }}
                aria-hidden="true"
              >
                {icon}
              </div>

              {/* Text */}
              <div>
                <h5 className="mb-1.5 font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
                  {title}
                </h5>
                <p className="text-[13px] leading-[1.5] text-ink-2">
                  {description}
                </p>
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}