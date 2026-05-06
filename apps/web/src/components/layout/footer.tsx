import Link from "next/link";

// ─── Types ────────────────────────────────────────────────────────────────────
interface FooterCol {
  heading: string;
  links:   { label: string; href: string }[];
}

// ─── Data ────────────────────────────────────────────────────────────────────
const COLS: FooterCol[] = [
  {
    heading: "Product",
    links: [
      { label: "How it works",    href: "#" },
      { label: "Career Twin",     href: "#" },
      { label: "Skill Graph",     href: "#" },
      { label: "Mock Interview",  href: "#" },
      { label: "Pricing",         href: "#pricing" },
    ],
  },
  {
    heading: "For",
    links: [
      { label: "Students",               href: "#" },
      { label: "Job seekers",            href: "#" },
      { label: "Career switchers",       href: "#" },
      { label: "Professionals",          href: "#" },
      { label: "Coaches & institutions", href: "#" },
    ],
  },
  {
    heading: "Resources",
    links: [
      { label: "Career library",      href: "#" },
      { label: "Roadmap templates",   href: "#" },
      { label: "Interview prep",      href: "#" },
      { label: "Salary benchmarks",   href: "#" },
      { label: "Newsletter",          href: "#" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "About",      href: "#" },
      { label: "Manifesto",  href: "#" },
      { label: "Privacy",    href: "#" },
      { label: "Security",   href: "#" },
      { label: "Contact",    href: "#" },
    ],
  },
];

const SOCIALS = [
  { label: "Twitter / X", href: "#" },
  { label: "LinkedIn",    href: "#" },
  { label: "GitHub",      href: "#" },
  { label: "Newsletter",  href: "#" },
];

// ─── Logo mark — light version (for dark background) ─────────────────────────
function FooterLogo() {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="h-7 w-7 shrink-0"
      aria-hidden="true"
    >
      {/* Path in bg cream */}
      <path
        d="M3 22 C 8 22, 8 6, 14 6 S 20 22, 25 22"
        stroke="#F7F2E8"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      {/* Start — terracotta */}
      <circle cx="3"  cy="22" r="2.2" fill="#C95A3D" />
      {/* Peak — green-soft (lighter on dark) */}
      <circle cx="14" cy="6"  r="2.2" fill="#DCE7DC" />
      {/* End — bg cream */}
      <circle cx="25" cy="22" r="2.2" fill="#F7F2E8" />
    </svg>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────
export function Footer() {
  return (
    <>
      <style>{`
        /* Footer grid responsive */
        .footer-grid-inner {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 40px;
          padding-bottom: 64px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        @media (min-width: 768px)  {
          .footer-grid-inner { grid-template-columns: 1fr 1fr 1fr; }
        }
        @media (min-width: 1024px) {
          .footer-grid-inner { grid-template-columns: 1.4fr 1fr 1fr 1fr 1fr; gap: 48px; }
        }

        /* Footer link hover */
        .footer-link {
          transition: color .15s ease;
          color: rgba(247,242,232,0.7);
        }
        .footer-link:hover { color: #F7F2E8; }

        /* Social link hover */
        .footer-social {
          transition: color .15s ease;
          color: rgba(247,242,232,0.55);
        }
        .footer-social:hover { color: #F7F2E8; }

        /* Brand wordmark hover */
        .footer-brand-link {
          transition: opacity .15s ease;
        }
        .footer-brand-link:hover { opacity: 0.85; }
      `}</style>

      <footer
        className="bg-ink px-6 pb-8 pt-20 sm:px-10 lg:px-12"
        aria-label="Site footer"
      >
        <div className="footer-grid-inner mx-auto max-w-[1280px]">

          {/* ── Brand column ────────────────────────────────────────── */}
          <div className="col-span-2 md:col-span-1 lg:col-span-1">
            <Link
              href="/"
              className="footer-brand-link mb-[18px] inline-flex items-center gap-2.5 font-serif text-[22px] font-medium tracking-[-0.01em] text-bg no-underline"
              aria-label="Career Roadmap AI — home"
            >
              <FooterLogo />
              Career Roadmap AI
            </Link>
            <p
              className="max-w-[280px] text-[13px] leading-[1.6]"
              style={{ color: "rgba(247,242,232,0.55)" }}
            >
              The global, AI-powered career intelligence platform. Personalised
              plans. Real-time market signals. Built for the long arc of a
              career.
            </p>
          </div>

          {/* ── Nav columns ─────────────────────────────────────────── */}
          {COLS.map(({ heading, links }) => (
            <div key={heading}>
              <h6
                className="mb-[18px] text-[11px] font-medium uppercase tracking-[0.14em]"
                style={{ color: "#F4DDD2" /* terra-soft */ }}
              >
                {heading}
              </h6>
              <nav aria-label={`${heading} links`}>
                {links.map(({ label, href }) => (
                  <Link
                    key={label}
                    href={href}
                    className="footer-link mb-2.5 block text-[13.5px]"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            </div>
          ))}
        </div>

        {/* ── Footer bottom bar ────────────────────────────────────── */}
        <div
          className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-4 pt-7 text-[12px]"
          style={{ color: "rgba(247,242,232,0.45)" }}
        >
          <p>© 2026 Career Roadmap AI · Made with care in Zürich.</p>

          <div className="flex items-center gap-[18px]">
            {SOCIALS.map(({ label, href }) => (
              <Link
                key={label}
                href={href}
                className="footer-social text-[12px]"
              >
                {label}
              </Link>
            ))}
          </div>
        </div>
      </footer>
    </>
  );
}