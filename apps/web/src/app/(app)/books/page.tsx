"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { booksApi, type Book, type BookStatus } from "@/lib/api/books";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";

const STATUS_CHIP: Record<BookStatus, string> = {
  reading: "bg-terra-soft text-terra-2",
  queued: "bg-bg-3 text-ink-2",
  done: "bg-green-soft text-green-2",
};

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export default function BooksPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [why, setWhy] = useState("");

  const { data: books, isLoading } = useQuery({
    queryKey: QUERY_KEYS.books,
    queryFn: booksApi.list,
    staleTime: 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: booksApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.books });
      toast.success("Book added");
      setTitle("");
      setAuthor("");
      setWhy("");
      setShowForm(false);
    },
    onError: () => toast.error("Couldn't add the book. Please try again."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    createMutation.mutate({ title: title.trim(), author: author.trim(), why: why.trim() });
  };

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Reading"
        title="Books"
        description="Curated reading mapped to your roadmap phases — each pick earns its place toward your goal."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            {showForm ? "Close" : "+ Add book"}
          </button>
        }
      />

      {showForm && (
        <form onSubmit={onSubmit} className="mb-6 space-y-3 rounded-[12px] border border-rule bg-paper p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className={FIELD_CLASS} />
            <input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Author" className={FIELD_CLASS} />
          </div>
          <input value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Why this book? (optional)" className={FIELD_CLASS} />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!title.trim() || createMutation.isPending}
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {createMutation.isPending ? "Adding…" : "Add to list"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your reading list…" />
      ) : !books || books.length === 0 ? (
        <EmptyState
          title="Your reading list is empty"
          description="Add the books that move you toward your target role — your roadmap can suggest more."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {books.map((b: Book) => (
            <Link
              key={b.id}
              href={`${ROUTES.books}/${b.id}`}
              className="group flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-5 transition-all duration-150 hover:border-rule-strong hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                {b.tag ? (
                  <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-ink-2">
                    {b.tag}
                  </span>
                ) : (
                  <span />
                )}
                <span className={`rounded-[5px] px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] ${STATUS_CHIP[b.status]}`}>
                  {b.status}
                </span>
              </div>
              <div className="min-w-0">
                <h3 className="font-serif text-[16px] font-medium leading-snug tracking-[-0.01em] text-ink">{b.title}</h3>
                {b.author && <p className="mt-0.5 text-[12.5px] text-ink-3">{b.author}</p>}
              </div>
              {b.why && <p className="line-clamp-3 text-[13px] leading-relaxed text-ink-2">{b.why}</p>}
              <span className="mt-auto text-[12px] font-medium text-ink-3 transition-colors group-hover:text-ink">
                Why this book →
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
