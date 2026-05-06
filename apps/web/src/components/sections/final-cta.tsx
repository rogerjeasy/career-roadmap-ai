"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

export function FinalCta() {
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

        /* Decorative corner circles */
        .final-cta-wrap::before,
        .final-cta-wrap::after {
          content: '';
          position: absolute;
          width: 200px; height: 200px;
          border: 1px solid #E0D7C2;
          border-radius: 50%;
          opacity: 0.5;
          pointer-events: none;
        }
        .final-cta-wrap::before { left: -80px; bottom: -80px; }
        .final-cta-wrap::after  { right: -80px; top: -80px; }

        /* Primary button */
        .final-btn-primary {
          transition: background .2s ease, transform .2s ease, box-shadow .2s ease;
        }
        .final-btn-primary:hover {
          background: #0E3A2B;
          transform: translateY(-1px);
          box-shadow: 0 6px 20px -4px rgba(19,78,58,0.45);
        }
        .final-btn-primary .arrow {
          display: inline-block;
          transition: transform .2s ease;
        }
        .final-btn-primary:hover .arrow { transform: translateX(3px); }

        /* Ghost button */
        .final-btn-ghost {
          transition: background .2s ease, border-color .2s ease;
        }
        .final-btn-ghost:hover {
          background: #FFFFFF;
          border-color: #15140F;
        }

        /* Responsive h2 */
        @media (max-width: 767px) {
          .final-cta-h2 { font-size: 64px !important; }
        }
      `}</style>

      <section
        ref={sectionRef}
        aria-labelledby="final-cta-heading"
        className="final-cta-wrap relative overflow-hidden border-t border-rule bg-bg px-6 text-center sm:px-12"
        style={{ padding: "140px 48px 160px" }}
      >
        {/* Vertical centre-line */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-rule"
        />

        {/* Ornament */}
        <p
          className="reveal relative z-10 mb-8 font-serif italic tracking-[0.05em] text-terra"
          style={{ fontSize: 14 }}
        >
          — Everyone deserves a serious plan —
        </p>

        {/* Heading */}
        <h2
          id="final-cta-heading"
          className="final-cta-h2 reveal relative z-10 mb-8 font-serif font-[350] leading-[0.95] tracking-[-0.04em] text-ink"
          style={{ fontSize: 96, transitionDelay: "0.1s" }}
        >
          Design your{" "}
          <em
            className="italic text-green"
            style={{ fontVariationSettings: '"opsz" 144' }}
          >
            career.
          </em>
        </h2>

        {/* Sub */}
        <p
          className="reveal relative z-10 mx-auto mb-11 max-w-[540px] text-[18px] leading-[1.55] text-ink-2"
          style={{ transitionDelay: "0.2s" }}
        >
          Free to start. Your plan is private by default. Cancel, export or
          delete your data at any time.
        </p>

        {/* CTA buttons */}
        <div
          className="reveal relative z-10 inline-flex flex-wrap justify-center gap-3.5 sm:gap-[14px]"
          style={{ transitionDelay: "0.3s" }}
        >
          <Link
            href="/register"
            className="final-btn-primary inline-flex items-center gap-2 rounded-full bg-green px-6 py-[14px] text-[15px] font-medium text-white"
          >
            Start your roadmap
            <span className="arrow">→</span>
          </Link>

          <Link
            href="/contact"
            className="final-btn-ghost inline-flex items-center rounded-full border border-rule-strong bg-transparent px-[22px] py-[13px] text-[15px] font-medium text-ink"
          >
            Talk to the team
          </Link>
        </div>
      </section>
    </>
  );
}