"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Plan {
  label:    string;
  price:    string;
  per:      string;
  desc:     string;
  features: string[];
  cta:      string;
  featured: boolean;
  badge?:   string;
}

// ─── Data ────────────────────────────────────────────────────────────────────
const PLANS: Plan[] = [
  {
    label:    "Starter",
    price:    "$0",
    per:      "/ month · always free",
    desc:     "Everything you need to build your first roadmap and understand your gaps.",
    features: [
      "AI-generated career roadmap (1 active)",
      "CV upload & gap analysis",
      "Weekly focus planner",
      "Job market pulse · 3 roles",
      "Career Health Score",
    ],
    cta:      "Get started free",
    featured: false,
  },
  {
    label:    "Pro",
    price:    "$19",
    per:      "/ month · billed annually",
    desc:     "The full career OS for professionals who are serious about their next move.",
    features: [
      "Unlimited roadmaps & phases",
      "Career Twin AI companion",
      "Adaptive Skill Graph",
      "What-If Scenario Simulator",
      "Mock Interview Studio · unlimited",
      "Live market pulse · unlimited roles",
      "Application tracker & outreach CRM",
      "Priority support",
    ],
    cta:      "Start 14-day free trial",
    featured: true,
    badge:    "Most popular",
  },
  {
    label:    "Teams & Coaches",
    price:    "$49",
    per:      "/ seat / month · min. 5 seats",
    desc:     "For career coaches, HR teams and universities managing cohorts at scale.",
    features: [
      "Everything in Pro, per seat",
      "Coach dashboard & client views",
      "Cohort analytics & reporting",
      "White-label ready",
      "SSO & advanced security",
      "Dedicated success manager",
    ],
    cta:      "Talk to sales →",
    featured: false,
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export function PricingSection() {
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

        /* Non-featured plan hover */
        .plan-card-plain {
          transition: background .25s ease;
        }
        .plan-card-plain:hover { background: #FFFFFF; }

        /* Non-featured CTA button */
        .cta-plain {
          transition: border-color .2s ease, background .2s ease;
        }
        .cta-plain:hover { border-color: #15140F; background: #EFE8D7; }

        /* Featured CTA button */
        .cta-featured {
          transition: background .2s ease;
        }
        .cta-featured:hover { background: #F4DDD2; }

        /* Responsive pricing grid */
        .pricing-grid-inner {
          display: grid;
          grid-template-columns: 1fr;
          border: 1px solid #C9BFA7;
          border-radius: 8px;
          overflow: hidden;
        }
        @media (min-width: 1024px) {
          .pricing-grid-inner { grid-template-columns: repeat(3, 1fr); }
        }

        /* On mobile stacked: last card has no bottom border */
        @media (max-width: 1023px) {
          .plan-card-plain, .plan-card-featured {
            border-right: none !important;
            border-bottom: 1px solid #C9BFA7;
          }
          .plan-last { border-bottom: none !important; }
        }
      `}</style>

      <section
        ref={sectionRef}
        id="pricing"
        aria-labelledby="pricing-heading"
        className="border-t border-rule bg-bg px-6 py-20 sm:px-10 sm:py-[120px] lg:px-12"
      >
        {/* ── Section header ────────────────────────────────────────── */}
        <div className="mx-auto mb-[72px] max-w-[880px] text-center">

          <p className="reveal mb-5 inline-block text-[12px] font-semibold uppercase tracking-[0.14em] text-terra">
            <em className="mr-2 font-serif text-[14px] font-medium not-italic">V.</em>
            Simple, transparent pricing
          </p>

          <h2
            id="pricing-heading"
            className="reveal mb-6 font-serif font-[350] leading-[1.02] tracking-[-0.025em] text-ink"
            style={{ fontSize: "clamp(32px, 4.5vw, 56px)", transitionDelay: "0.1s" }}
          >
            Start free. Grow{" "}
            <em className="italic text-green">with your career.</em>
          </h2>

          <p
            className="reveal mx-auto max-w-[660px] text-[18px] leading-[1.55] text-ink-2"
            style={{ transitionDelay: "0.2s" }}
          >
            No hidden fees. Export your data anytime. Cancel in one click.
            Your plan belongs to you.
          </p>
        </div>

        {/* ── Pricing grid ──────────────────────────────────────────── */}
        <div
          className="pricing-grid-inner reveal mx-auto max-w-[1280px]"
          style={{ transitionDelay: "0.1s" }}
          role="list"
          aria-label="Pricing plans"
        >
          {PLANS.map(({ label, price, per, desc, features, cta, featured, badge }, idx) => (
            <div
              key={label}
              role="listitem"
              className={[
                "relative flex flex-col",
                "px-9 pb-11 pt-10",
                featured
                  ? "plan-card-featured bg-green"
                  : "plan-card-plain bg-bg",
                !featured && idx < PLANS.length - 1
                  ? "border-r border-rule-strong"
                  : "",
                featured
                  ? ""
                  : "",
                idx === PLANS.length - 1 ? "plan-last" : "",
              ].filter(Boolean).join(" ")}
              style={
                featured
                  ? { borderRight: "1px solid rgba(255,255,255,0.12)" }
                  : undefined
              }
            >
              {/* Most popular badge */}
              {badge && (
                <div
                  className="absolute left-1/2 top-[-1px] -translate-x-1/2 rounded-b-[8px] bg-terra px-[14px] py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-white"
                >
                  {badge}
                </div>
              )}

              {/* Plan label */}
              <p
                className="mb-5 text-[11px] font-semibold uppercase tracking-[0.14em]"
                style={{ color: featured ? "rgba(220,231,220,0.75)" : "#C95A3D" }}
              >
                {label}
              </p>

              {/* Price */}
              <p
                className="mb-1 font-serif font-[350] leading-none tracking-[-0.03em]"
                style={{
                  fontSize: 52,
                  color: featured ? "#ffffff" : "#15140F",
                }}
              >
                {price}
              </p>

              {/* Per */}
              <p
                className="mb-6 text-[13px]"
                style={{ color: featured ? "rgba(220,231,220,0.7)" : "#8A8170" }}
              >
                {per}
              </p>

              {/* Description */}
              <p
                className="mb-8 border-b pb-7 text-[14px] leading-[1.55]"
                style={{
                  color:       featured ? "rgba(220,231,220,0.8)" : "#4D4639",
                  borderColor: featured ? "rgba(255,255,255,0.12)" : "#E0D7C2",
                }}
              >
                {desc}
              </p>

              {/* Features */}
              <ul
                className="mb-9 mt-auto flex flex-col gap-3"
                aria-label={`${label} plan features`}
              >
                {features.map((f) => (
                  <li
                    key={f}
                    className="flex items-start gap-2.5 text-[13.5px]"
                    style={{ color: featured ? "rgba(220,231,220,0.88)" : "#4D4639" }}
                  >
                    <span
                      className="mt-px shrink-0 font-semibold"
                      style={{ color: featured ? "#F4DDD2" : "#134E3A" }}
                      aria-hidden="true"
                    >
                      ✓
                    </span>
                    {f}
                  </li>
                ))}
              </ul>

              {/* CTA button */}
              {featured ? (
                <Link
                  href="/register"
                  className="cta-featured block rounded-full bg-white py-[13px] text-center text-[14px] font-medium text-green-2"
                >
                  {cta}
                </Link>
              ) : (
                <Link
                  href={label === "Teams & Coaches" ? "/contact" : "/register"}
                  className="cta-plain block rounded-full border-[1.5px] border-rule-strong bg-transparent py-[13px] text-center text-[14px] font-medium text-ink"
                >
                  {cta}
                </Link>
              )}
            </div>
          ))}
        </div>

        {/* ── Pricing note ──────────────────────────────────────────── */}
        <p
          className="reveal mt-6 text-center text-[13px] text-ink-3"
          style={{ transitionDelay: "0.2s" }}
        >
          All plans include a 14-day free trial on Pro. No credit card required
          to start. ·{" "}
          <Link
            href="#"
            className="text-terra underline underline-offset-[3px] transition-colors hover:text-terra-2"
          >
            Compare all features →
          </Link>
        </p>
      </section>
    </>
  );
}