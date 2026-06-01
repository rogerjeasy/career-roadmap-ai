"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { booksApi } from "@/lib/api/books";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";

export default function BookDetailPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;

  const { data: book, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.book(bookId),
    queryFn: () => booksApi.get(bookId),
    enabled: Boolean(bookId),
  });

  const backLink = (
    <Link
      href={ROUTES.books}
      className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
    >
      ← Books
    </Link>
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[720px] px-7 pb-24 pt-7">
        {backLink}
        <LoadingSpinner fullPage label="Loading…" />
      </div>
    );
  }

  if (isError || !book) {
    return (
      <div className="mx-auto max-w-[720px] px-7 pb-24 pt-7">
        {backLink}
        <EmptyState
          title="Book not found"
          description="This book isn't in your reading list."
          action={
            <Link
              href={ROUTES.books}
              className="inline-flex items-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Back to books
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[720px] px-7 pb-24 pt-7">
      {backLink}
      <PageHeader eyebrow={book.author || "Reading"} title={book.title} />

      {book.phase && (
        <p className="mb-5 inline-flex items-center rounded-[6px] bg-green-faint px-2.5 py-1 text-[12px] font-medium text-green-2">
          {book.phase}
        </p>
      )}

      <div className="rounded-[12px] border border-rule bg-paper p-6">
        <h2 className="mb-2 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">Why this book</h2>
        <p className="text-[13.5px] leading-relaxed text-ink-2">
          {book.why || "A rationale for this book will appear here once your roadmap links it to a phase."}
        </p>

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
