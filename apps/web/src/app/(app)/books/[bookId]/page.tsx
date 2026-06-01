"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";

interface BookDetail {
  id: string;
  title: string;
  author: string;
  why: string;
  phase: string;
  takeaways: string[];
}

const DETAILS: Record<string, BookDetail> = {
  "designing-ml-systems": {
    id: "designing-ml-systems",
    title: "Designing Machine Learning Systems",
    author: "Chip Huyen",
    why: "This book sits at the exact intersection of your current full-stack skills and your target AI systems role. It teaches you to think about ML as a system — data, deployment, monitoring — not just models.",
    phase: "Phase 02 · Specialisation in applied ML",
    takeaways: [
      "Frame ML problems as end-to-end systems with feedback loops",
      "Design data pipelines that are reliable and observable",
      "Reason about deployment, drift, and monitoring trade-offs",
    ],
  },
};

export default function BookDetailPage() {
  const params = useParams<{ bookId: string }>();
  const book =
    DETAILS[params.bookId] ?? {
      id: params.bookId,
      title: "Book",
      author: "",
      why: "A full rationale for this recommendation will appear here once your roadmap links it to a phase.",
      phase: "",
      takeaways: [],
    };

  return (
    <div className="mx-auto max-w-[720px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.books}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Books
      </Link>
      <PageHeader eyebrow={book.author || "Reading"} title={book.title} />

      {book.phase && (
        <p className="mb-5 inline-flex items-center rounded-[6px] bg-green-faint px-2.5 py-1 text-[12px] font-medium text-green-2">
          {book.phase}
        </p>
      )}

      <div className="rounded-[12px] border border-rule bg-paper p-6">
        <h2 className="mb-2 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">Why this book</h2>
        <p className="text-[13.5px] leading-relaxed text-ink-2">{book.why}</p>

        {book.takeaways.length > 0 && (
          <>
            <h2 className="mb-2 mt-5 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
              What you&apos;ll take away
            </h2>
            <ul className="space-y-2">
              {book.takeaways.map((t, i) => (
                <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug text-ink-2">
                  <span className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-green" aria-hidden="true" />
                  <span className="min-w-0">{t}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
