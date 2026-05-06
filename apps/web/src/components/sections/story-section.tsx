"use client";

import { useEffect, useRef } from "react";

export function StorySection() {
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
        /* Reveal */
        .reveal { opacity:0; transform:translateY(22px); transition: opacity .7s cubic-bezier(.2,.7,.2,1), transform .7s cubic-bezier(.2,.7,.2,1); }
        .reveal.visible { opacity:1; transform:translateY(0); }

        /* story-img decorative layers */
        .story-img-wrap::before {
          content: ""; position: absolute; inset: 0; z-index: 1;
          background-image:
            linear-gradient(rgba(247,242,232,0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(247,242,232,0.04) 1px, transparent 1px);
          background-size: 32px 32px;
          background-position: -1px -1px;
        }
        .story-img-wrap::after {
          content: ""; position: absolute; inset: 0; z-index: 2;
          background:
            radial-gradient(circle at 75% 28%, rgba(244,221,210,0.22) 0%, transparent 45%),
            radial-gradient(circle at 18% 82%, rgba(201,90,61,0.18)   0%, transparent 50%);
        }

        /* ID-strip live dot */
        @keyframes idpulse {
          0%,100% { box-shadow: 0 0 0 0 rgba(201,90,61,0.8); }
          70%      { box-shadow: 0 0 0 8px rgba(201,90,61,0); }
        }
        .id-live-dot { animation: idpulse 2s infinite; }

        /* Floating skill chips */
        @keyframes floaty {
          0%,100% { transform: translateY(0); }
          50%      { transform: translateY(-6px); }
        }
        .chip-float { animation: floaty 5s ease-in-out infinite; }
        .chip-float-d1 { animation-delay: 0s; }
        .chip-float-d2 { animation-delay: 1.2s; }
        .chip-float-d3 { animation-delay: 2.4s; }

        /* Responsive grid */
        .story-grid-wrap { display: grid; grid-template-columns: 0.9fr 1.1fr; gap: 80px; align-items: center; }
        @media (max-width: 1023px) {
          .story-grid-wrap { grid-template-columns: 1fr; gap: 48px; }
        }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="story-label"
        className="bg-bg px-6 sm:px-12"
        style={{ padding: "140px 48px 120px" }}
      >
        <div className="story-grid-wrap mx-auto max-w-[1280px]">

          {/* ── LEFT: Visual card ─────────────────────────────────────── */}
          <div
            className="reveal story-img-wrap relative overflow-hidden rounded-[6px]"
            style={{
              aspectRatio: "4/5",
              background: "#1a4234",
              boxShadow:
                "0 24px 60px -24px rgba(19,78,58,0.45), 0 0 0 1px #E0D7C2",
            }}
          >

            {/* ── ID strip ────────────────────────────────────────── */}
            <div
              className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between border-b px-[22px] py-4 text-[10.5px] uppercase tracking-[0.14em] backdrop-blur-sm"
              style={{
                color: "rgba(247,242,232,0.65)",
                borderColor: "rgba(247,242,232,0.08)",
                background: "rgba(0,0,0,0.12)",
              }}
            >
              <span>Member · CR-2024-09147</span>
              <span
                className="flex items-center gap-[7px]"
                style={{ color: "#F4DDD2" }}
              >
                <span
                  className="id-live-dot h-1.5 w-1.5 rounded-full bg-terra"
                  aria-hidden="true"
                />
                Active plan
              </span>
            </div>

            {/* ── Location pin ─────────────────────────────────────── */}
            <div
              className="absolute z-10 inline-flex items-center gap-[5px] rounded-[4px] bg-terra px-[11px] py-[6px] text-[11px] font-semibold tracking-[0.04em] text-white"
              style={{
                top: "18%",
                right: "7%",
                boxShadow: "0 6px 18px -4px rgba(201,90,61,0.5)",
              }}
            >
              <svg
                viewBox="0 0 12 12"
                fill="currentColor"
                className="h-[11px] w-[11px] shrink-0"
                aria-hidden="true"
              >
                <path d="M6 1c-2.2 0-4 1.8-4 4 0 3 4 6 4 6s4-3 4-6c0-2.2-1.8-4-4-4zm0 5.5c-.8 0-1.5-.7-1.5-1.5S5.2 3.5 6 3.5s1.5.7 1.5 1.5S6.8 6.5 6 6.5z" />
              </svg>
              Bangalore, IN
            </div>

            {/* ── Floating skill chips ──────────────────────────────── */}
            {/* Chip 1 — green */}
            <span
              className="chip-float chip-float-d1 absolute z-10 inline-flex items-center gap-1.5 rounded-full px-3 py-[7px] text-[11px] font-medium text-ink"
              style={{
                top: "26%",
                left: "6%",
                background: "rgba(247,242,232,0.95)",
                boxShadow: "0 6px 16px -4px rgba(0,0,0,0.2)",
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-green" aria-hidden="true" />
              RAG systems
            </span>

            {/* Chip 2 — terra */}
            <span
              className="chip-float chip-float-d2 absolute z-10 inline-flex items-center gap-1.5 rounded-full px-3 py-[7px] text-[11px] font-medium text-ink"
              style={{
                top: "46%",
                right: "4%",
                background: "rgba(247,242,232,0.95)",
                boxShadow: "0 6px 16px -4px rgba(0,0,0,0.2)",
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-terra" aria-hidden="true" />
              PyTorch · prod
            </span>

            {/* Chip 3 — gold */}
            <span
              className="chip-float chip-float-d3 absolute z-10 inline-flex items-center gap-1.5 rounded-full px-3 py-[7px] text-[11px] font-medium text-ink"
              style={{
                top: "70%",
                left: "4%",
                background: "rgba(247,242,232,0.95)",
                boxShadow: "0 6px 16px -4px rgba(0,0,0,0.2)",
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-gold" aria-hidden="true" />
              Open-source · 14 PRs
            </span>

            {/* ── Health score stat tile ────────────────────────────── */}
            <div
              className="absolute z-10 flex items-center gap-2.5 rounded-[8px] px-3.5 py-2.5 text-[11px]"
              style={{
                bottom: 86,
                left: 20,
                background: "rgba(247,242,232,0.97)",
                color: "#15140F",
                boxShadow: "0 10px 24px -8px rgba(0,0,0,0.25)",
              }}
            >
              {/* Conic arc */}
              <div
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                style={{
                  background:
                    "conic-gradient(#134E3A 0deg 268deg, #DCE7DC 268deg 360deg)",
                }}
              >
                <span
                  className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-white font-serif text-[11px] font-semibold"
                >
                  87
                </span>
              </div>
              <div>
                <div
                  className="mb-0.5 text-[10px] uppercase tracking-[0.06em]"
                  style={{ color: "#8A8170" }}
                >
                  Health Score
                </div>
                <div className="font-serif text-[14px] font-medium">+15 this qtr</div>
              </div>
            </div>

            {/* ── Portrait SVG ──────────────────────────────────────── */}
            <div
              className="absolute z-[3]"
              style={{
                left: "50%",
                top: "48%",
                transform: "translate(-50%, -50%)",
                width: "64%",
              }}
              aria-hidden="true"
            >
              <svg viewBox="0 0 240 280" xmlns="http://www.w3.org/2000/svg" style={{ width: "100%", height: "auto", display: "block" }}>
                <defs>
                  <radialGradient id="story-halo">
                    <stop offset="0%"   stopColor="#F4DDD2" stopOpacity="0.5" />
                    <stop offset="100%" stopColor="#F4DDD2" stopOpacity="0" />
                  </radialGradient>
                  <linearGradient id="story-bodyGrad" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%"   stopColor="#F7F2E8" />
                    <stop offset="100%" stopColor="#EFE8D7" />
                  </linearGradient>
                  <linearGradient id="story-hairGrad" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%"   stopColor="#15140F" />
                    <stop offset="100%" stopColor="#2a2620" />
                  </linearGradient>
                </defs>

                {/* Soft outer halo */}
                <ellipse cx="120" cy="98" rx="78" ry="82" fill="url(#story-halo)" opacity="0.55" />

                {/* Shoulders / body */}
                <path d="M 30 280 C 30 220, 70 188, 120 188 C 170 188, 210 220, 210 280 Z" fill="url(#story-bodyGrad)" />

                {/* Collar detail */}
                <path d="M 95 196 L 120 220 L 145 196" stroke="#C95A3D" strokeWidth="2" fill="none" opacity="0.6" />
                <circle cx="120" cy="226" r="2" fill="#C95A3D" opacity="0.8" />

                {/* Neck */}
                <path d="M 105 178 L 105 200 Q 120 210, 135 200 L 135 178 Z" fill="#E8DFC8" />

                {/* Head */}
                <ellipse cx="120" cy="125" rx="48" ry="56" fill="#E8DFC8" />

                {/* Hair (back layer) */}
                <path
                  d="M 70 110 C 70 78, 88 60, 120 60 C 152 60, 172 78, 172 110 C 172 130, 168 145, 165 152 C 162 142, 156 130, 150 124 C 150 100, 138 88, 120 88 C 102 88, 90 100, 90 124 C 84 130, 78 142, 75 152 C 72 145, 70 130, 70 110 Z"
                  fill="url(#story-hairGrad)"
                />

                {/* Hair side strand */}
                <path
                  d="M 165 130 C 168 145, 172 165, 168 178 L 162 175 C 162 162, 162 145, 162 135 Z"
                  fill="url(#story-hairGrad)"
                />

                {/* Face shadow */}
                <path d="M 88 130 Q 90 165, 105 178 Q 92 168, 84 145 Z" fill="#15140F" opacity="0.06" />

                {/* Earring */}
                <circle cx="166" cy="138" r="2" fill="#B68A2E" />
                <circle cx="166" cy="138" r="3.5" fill="none" stroke="#B68A2E" strokeWidth="0.5" opacity="0.6" />

                {/* Decorative orbital ring */}
                <ellipse cx="120" cy="125" rx="86" ry="92" fill="none" stroke="#F7F2E8" strokeWidth="1" strokeDasharray="2 6" opacity="0.25" />

                {/* Milestone dots on ring */}
                <circle cx="34"  cy="125" r="3" fill="#C95A3D" />
                <circle cx="206" cy="125" r="3" fill="#F7F2E8" />
                <circle cx="120" cy="33"  r="3" fill="#B68A2E" />
              </svg>
            </div>

            {/* ── Name tag (bottom) ─────────────────────────────────── */}
            <div
              className="absolute bottom-0 left-0 right-0 z-10 flex items-end justify-between gap-3 px-6 pb-[22px] pt-16 text-bg"
              style={{
                background:
                  "linear-gradient(180deg, transparent 0%, rgba(11,35,27,0.9) 60%)",
              }}
            >
              <div>
                <div
                  className="mb-1.5 font-serif leading-none tracking-[-0.01em]"
                  style={{ fontSize: 26, fontWeight: 450 }}
                >
                  Maya R.
                </div>
                <div className="text-[12.5px] leading-[1.3] tracking-[0.01em] opacity-[0.88]">
                  Senior Backend Eng.{" "}
                  <em className="not-italic" style={{ color: "#F4DDD2" }}>→</em>{" "}
                  ML Engineer
                </div>
              </div>
              <div
                className="shrink-0 pb-[3px] text-right text-[10px] uppercase tracking-[0.12em] opacity-55"
              >
                Member since
                <b className="mt-0.5 block text-[12px] font-semibold tracking-[0.04em] opacity-100">
                  Apr 2025
                </b>
              </div>
            </div>
          </div>

          {/* ── RIGHT: Story text ─────────────────────────────────────── */}
          <div>
            {/* Label */}
            <p
              id="story-label"
              className="reveal mb-6 text-[12px] font-semibold uppercase tracking-[0.14em] text-terra"
            >
              Member story · 12 months in
            </p>

            {/* Pull quote */}
            <blockquote
              className="reveal mb-9 font-serif font-[350] leading-[1.18] tracking-[-0.018em] text-ink"
              style={{ fontSize: "clamp(24px, 3vw, 38px)", transitionDelay: "0.1s" }}
            >
              &ldquo;I went in as a backend engineer with no production ML
              experience. Twelve months later I had a portfolio, an open-source
              contribution, two offers, and a coach that{" "}
              <em className="italic text-green">
                negotiated my salary with me
              </em>
              , not for me.&rdquo;
            </blockquote>

            {/* Stats */}
            <div
              className="grid grid-cols-3 gap-6 border-t border-rule pt-8"
              role="list"
              aria-label="Member outcomes"
            >
              {/* Stat 1 */}
              <div className="reveal" style={{ transitionDelay: "0.1s" }} role="listitem">
                <div
                  className="mb-2 font-serif font-normal leading-none tracking-[-0.02em] text-ink"
                  style={{ fontSize: 40 }}
                >
                  <em className="italic text-terra">14</em>
                </div>
                <p className="text-[12px] leading-[1.4] text-ink-2">
                  Milestones completed across three career phases
                </p>
              </div>

              {/* Stat 2 */}
              <div className="reveal" style={{ transitionDelay: "0.2s" }} role="listitem">
                <div
                  className="mb-2 font-serif font-normal leading-none tracking-[-0.02em] text-ink"
                  style={{ fontSize: 40 }}
                >
                  <em className="italic text-terra">2</em>
                </div>
                <p className="text-[12px] leading-[1.4] text-ink-2">
                  Offers received from remote-friendly ML startups
                </p>
              </div>

              {/* Stat 3 */}
              <div className="reveal" style={{ transitionDelay: "0.3s" }} role="listitem">
                <div
                  className="mb-2 font-serif font-normal leading-none tracking-[-0.02em] text-ink"
                  style={{ fontSize: 40 }}
                >
                  <em className="italic text-terra">
                    +38<span style={{ fontSize: 18 }}>%</span>
                  </em>
                </div>
                <p className="text-[12px] leading-[1.4] text-ink-2">
                  Compensation uplift on signed offer vs. previous role
                </p>
              </div>
            </div>
          </div>

        </div>
      </section>
    </>
  );
}