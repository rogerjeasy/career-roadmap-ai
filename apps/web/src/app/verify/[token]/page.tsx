"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { credentialsApi } from "@/lib/api/credentials";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { cn } from "@/lib/utils";

const LEVEL_LABEL: Record<string, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};

export default function VerifyCredentialPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const { data: result, isLoading, isError } = useQuery({
    queryKey: ["credential-verify", token],
    queryFn: () => credentialsApi.verify(token),
    enabled: Boolean(token),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-[640px] items-center justify-center px-6">
        <LoadingSpinner label="Verifying credential…" />
      </div>
    );
  }

  if (isError || !result) {
    return (
      <div className="mx-auto max-w-[640px] px-6 py-20 text-center">
        <h1 className="font-serif text-[24px] font-medium text-ink">
          Couldn&apos;t verify this credential
        </h1>
        <p className="mt-2 text-[13.5px] text-ink-2">
          The link may be incomplete or the service is temporarily unavailable.
        </p>
      </div>
    );
  }

  const valid = result.valid;
  const revoked = result.status === "revoked";

  return (
    <div className="mx-auto max-w-[640px] px-6 py-12 sm:py-16">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-terra">
        Verified Credential
      </p>

      <div
        className={cn(
          "rounded-[14px] border bg-paper p-6 sm:p-8",
          valid ? "border-green" : "border-rule-strong",
        )}
      >
        <div className="mb-5 flex items-center gap-3">
          <span
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-full text-[16px] font-bold text-bg",
              valid ? "bg-green" : "bg-ink-3",
            )}
          >
            {valid ? "✓" : revoked ? "⊘" : "!"}
          </span>
          <span
            className={cn(
              "text-[13px] font-semibold",
              valid ? "text-green-2" : "text-ink-2",
            )}
          >
            {valid ? "Authentic & intact" : revoked ? "Revoked" : "Not valid"}
          </span>
        </div>

        {result.skill ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {result.level && (
                <span className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-green-2">
                  {LEVEL_LABEL[result.level] ?? result.level}
                </span>
              )}
              <h1 className="font-serif text-[26px] font-medium leading-tight tracking-[-0.02em] text-ink">
                {result.skill}
              </h1>
            </div>
            {result.holderName && (
              <p className="mt-2 text-[14px] text-ink-2">
                Held by{" "}
                <span className="font-medium text-ink">{result.holderName}</span>
              </p>
            )}
            {result.summary && (
              <p className="mt-4 text-[13.5px] leading-relaxed text-ink-2">
                {result.summary}
              </p>
            )}

            <div className="mt-6 border-t border-rule pt-5">
              <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                Backed by {result.evidenceCount} evidence item
                {result.evidenceCount === 1 ? "" : "s"}
              </p>
              <div className="mt-3 space-y-2">
                {result.evidence.map((e) => (
                  <div
                    key={e.evidenceId}
                    className="flex items-start justify-between gap-3 rounded-[9px] border border-rule bg-bg px-3.5 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-ink">
                        {e.title}
                      </p>
                      <p className="text-[11.5px] text-ink-3">
                        {e.type}
                        {e.dateLabel ? ` · ${e.dateLabel}` : ""}
                      </p>
                    </div>
                    {e.link && (
                      <a
                        href={e.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="shrink-0 text-[12px] font-medium text-terra transition-colors hover:text-terra-2"
                      >
                        Proof →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}

        <p className="mt-6 rounded-[9px] bg-bg-2 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-ink-2">
          {result.reason}
        </p>
      </div>

      <p className="mt-6 text-center text-[12px] text-ink-3">
        Verified by{" "}
        <Link href="/" className="font-medium text-ink transition-colors hover:text-terra">
          Career Roadmap AI
        </Link>
      </p>
    </div>
  );
}
