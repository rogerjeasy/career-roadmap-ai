"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ossApi, type OssIssue, type OssBookmark } from "@/lib/api/oss";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

type Tab = "find" | "saved";

export default function OpenSourcePage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("find");
  const [language, setLanguage] = useState("");
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState({ language: "", query: "", active: false });

  const { data: result, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.ossSearch(submitted.language, submitted.query),
    queryFn: () => ossApi.search(submitted.language, submitted.query),
    enabled: submitted.active,
    retry: false,
    staleTime: 60 * 1000,
  });

  const { data: bookmarks } = useQuery({
    queryKey: QUERY_KEYS.ossBookmarks,
    queryFn: ossApi.listBookmarks,
    staleTime: 30 * 1000,
  });

  const bookmarkedIds = new Set((bookmarks ?? []).map((b) => b.issueId));

  const addMutation = useMutation({
    mutationFn: (issue: OssIssue) =>
      ossApi.addBookmark({
        issueId: issue.issueId,
        title: issue.title,
        url: issue.url,
        repo: issue.repo,
        language: issue.language,
        labels: issue.labels,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.ossBookmarks });
      toast.success("Saved to your contributions");
    },
    onError: () => toast.error("Couldn't save that issue."),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      ossApi.updateStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.ossBookmarks }),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => ossApi.removeBookmark(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.ossBookmarks });
      toast.success("Removed");
    },
  });

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted({ language: language.trim(), query: query.trim(), active: true });
  };

  return (
    <div className="mx-auto max-w-[880px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Build proof"
        title="Open-Source Finder"
        description="Turn your skills into a public track record. Search live “good first issue” tickets on GitHub, ranked to your skills, and bookmark the ones you'll tackle."
      />

      <div className="mb-6 flex gap-1 rounded-[9px] border border-rule bg-bg-2 p-1">
        {(["find", "saved"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-150",
              tab === t ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
            )}
          >
            {t === "find" ? "Find issues" : `Saved${bookmarks?.length ? ` (${bookmarks.length})` : ""}`}
          </button>
        ))}
      </div>

      {tab === "find" ? (
        <>
          <form onSubmit={onSearch} className="mb-6 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <input
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              placeholder="Language (blank = from your skills)"
              className={FIELD_CLASS}
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Keyword (optional)"
              className={FIELD_CLASS}
            />
            <button
              type="submit"
              className="rounded-[7px] bg-ink px-5 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2"
            >
              Search
            </button>
          </form>

          {!submitted.active ? (
            <EmptyState
              title="Search for your first issue"
              description="Leave the language blank to use the skills on your profile, or type one in. We'll pull live good-first-issues from GitHub."
            />
          ) : isLoading ? (
            <LoadingSpinner fullPage label="Searching GitHub…" />
          ) : isError ? (
            <EmptyState
              title="Search failed"
              description="GitHub may be rate-limiting anonymous searches. Wait a moment and try again."
            />
          ) : !result || result.issues.length === 0 ? (
            <EmptyState
              title="No issues found"
              description={result?.note || "Try a different language or keyword."}
            />
          ) : (
            <div className="space-y-3">
              {result.languagesUsed.length > 0 && (
                <p className="text-[12px] text-ink-3">
                  Showing {result.languagesUsed.join(", ")} good-first-issues
                </p>
              )}
              {result.issues.map((issue: OssIssue) => (
                <article
                  key={issue.issueId}
                  className="rounded-[12px] border border-rule bg-paper p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <a
                        href={issue.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-serif text-[15.5px] font-medium leading-snug tracking-[-0.01em] text-ink transition-colors hover:text-terra"
                      >
                        {issue.title}
                      </a>
                      <p className="mt-0.5 text-[12px] text-ink-3">
                        {issue.repo} · {issue.comments} comments
                      </p>
                    </div>
                    <span className="shrink-0 rounded-[6px] bg-green-soft px-2.5 py-1 text-[12px] font-semibold text-green-2">
                      {issue.matchScore}%
                    </span>
                  </div>
                  {issue.matchReason && (
                    <p className="mt-2 text-[12.5px] italic text-ink-3">{issue.matchReason}</p>
                  )}
                  {issue.labels.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {issue.labels.slice(0, 6).map((l) => (
                        <span
                          key={l}
                          className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[11px] font-medium text-ink-2"
                        >
                          {l}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      onClick={() => addMutation.mutate(issue)}
                      disabled={bookmarkedIds.has(issue.issueId) || addMutation.isPending}
                      className="rounded-[7px] border border-rule px-3.5 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:border-rule-strong disabled:opacity-50"
                    >
                      {bookmarkedIds.has(issue.issueId) ? "Saved ✓" : "Save"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      ) : !bookmarks || bookmarks.length === 0 ? (
        <EmptyState
          title="No saved issues yet"
          description="Bookmark issues from “Find issues” to build your contribution shortlist and track progress."
        />
      ) : (
        <div className="space-y-3">
          {bookmarks.map((b: OssBookmark) => (
            <article key={b.id} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <a
                    href={b.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink transition-colors hover:text-terra"
                  >
                    {b.title}
                  </a>
                  <p className="mt-0.5 text-[12px] text-ink-3">{b.repo}</p>
                </div>
                <select
                  value={b.status}
                  onChange={(e) => statusMutation.mutate({ id: b.id, status: e.target.value })}
                  className="shrink-0 rounded-[6px] border border-rule bg-bg px-2.5 py-1 text-[12px] text-ink focus:border-green focus:outline-none"
                >
                  <option value="saved">Saved</option>
                  <option value="in_progress">In progress</option>
                  <option value="submitted">PR submitted</option>
                  <option value="merged">Merged</option>
                </select>
              </div>
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={() => removeMutation.mutate(b.id)}
                  className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
