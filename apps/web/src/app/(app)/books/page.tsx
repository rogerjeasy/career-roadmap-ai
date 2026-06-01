"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";

interface Book {
  id: string;
  title: string;
  author: string;
  why: string;
  status: "reading" | "queued" | "done";
  tag: string;
}

const BOOKS: Book[] = [
  { id: "designing-ml-systems", title: "Designing Machine Learning Systems", author: "Chip Huyen", why: "Bridges ML and systems engineering — directly relevant to your target role.", status: "reading", tag: "Core" },
  { id: "building-llm-apps", title: "Building LLM-Powered Applications", author: "Valentina Alto", why: "Practical patterns for the kind of agentic apps in your portfolio.", status: "queued", tag: "Applied" },
  { id: "staff-engineer", title: "The Staff Engineer's Path", author: "Tanya Reilly", why: "Sets expectations for the seniority band you're aiming for.", status: "queued", tag: "Career" },
  { id: "deep-learning", title: "Deep Learning", author: "Goodfellow et al.", why: "Reference for the fundamentals behind your applied work.", status: "done", tag: "Foundations" },
];

const STATUS_CHIP: Record<Book["status"], string> = {
  reading: "bg-terra-soft text-terra-2",
  queued: "bg-bg-3 text-ink-2",
  done: "bg-green-soft text-green-2",
};

export default function BooksPage() {
  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Reading"
        title="Books"
        description="Curated reading mapped to your roadmap phases — each pick earns its place toward your goal."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        {BOOKS.map((b) => (
          <Link
            key={b.id}
            href={`${ROUTES.books}/${b.id}`}
            className="group flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5 transition-all duration-150 hover:border-rule-strong hover:shadow-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-ink-2">
                {b.tag}
              </span>
              <span className={`rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] ${STATUS_CHIP[b.status]}`}>
                {b.status}
              </span>
            </div>
            <div className="min-w-0">
              <h3 className="font-serif text-[16px] font-medium leading-snug tracking-[-0.01em] text-ink">{b.title}</h3>
              <p className="mt-0.5 text-[12.5px] text-ink-3">{b.author}</p>
            </div>
            <p className="line-clamp-3 text-[13px] leading-relaxed text-ink-2">{b.why}</p>
            <span className="mt-auto text-[12px] font-medium text-ink-3 transition-colors group-hover:text-ink">
              Why this book →
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
