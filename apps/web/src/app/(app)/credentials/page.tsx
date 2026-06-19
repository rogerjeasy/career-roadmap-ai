"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  credentialsApi,
  type Credential,
  type CredentialLevel,
} from "@/lib/api/credentials";
import { evidenceApi, type Evidence } from "@/lib/api/evidence";
import { QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const LEVELS: { value: CredentialLevel; label: string }[] = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
  { value: "expert", label: "Expert" },
];

const LEVEL_LABEL: Record<CredentialLevel, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};

export default function CredentialsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [skill, setSkill] = useState("");
  const [level, setLevel] = useState<CredentialLevel>("intermediate");
  const [summary, setSummary] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<string[]>([]);
  const [pendingRevoke, setPendingRevoke] = useState<Credential | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Credential | null>(null);

  const { data: credentials, isLoading } = useQuery({
    queryKey: QUERY_KEYS.credentials,
    queryFn: credentialsApi.list,
    staleTime: 60 * 1000,
  });

  const { data: evidence } = useQuery({
    queryKey: QUERY_KEYS.evidence,
    queryFn: evidenceApi.list,
    staleTime: 60 * 1000,
  });

  const resetForm = () => {
    setSkill("");
    setLevel("intermediate");
    setSummary("");
    setSelectedEvidence([]);
    setShowForm(false);
  };

  const issueMutation = useMutation({
    mutationFn: credentialsApi.issue,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.credentials });
      toast.success("Credential issued");
      resetForm();
    },
    onError: () => toast.error("Couldn't issue that credential. Please try again."),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.credentials });
      toast.success("Credential revoked");
      setPendingRevoke(null);
    },
    onError: () => toast.error("Couldn't revoke that credential."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.credentials });
      toast.success("Credential deleted");
      setPendingDelete(null);
    },
    onError: () => toast.error("Couldn't delete that credential."),
  });

  const toggleEvidence = (id: string) => {
    setSelectedEvidence((prev) =>
      prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id],
    );
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!skill.trim() || selectedEvidence.length === 0) return;
    issueMutation.mutate({
      skill: skill.trim(),
      level,
      summary: summary.trim(),
      evidenceIds: selectedEvidence,
    });
  };

  const copyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Verification link copied");
    } catch {
      toast.error("Couldn't copy the link");
    }
  };

  const hasEvidence = Boolean(evidence && evidence.length > 0);

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Assets"
        title="Skill Credentials"
        description="Mint signed, shareable credentials that attest to a skill and embed the real evidence behind it. Anyone with the link can verify a credential is genuine and unaltered — no login required."
        actions={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            disabled={!hasEvidence}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            {showForm ? "Close" : "+ Issue credential"}
          </button>
        }
      />

      {!hasEvidence && (
        <p className="mb-6 rounded-[10px] border border-rule bg-bg-2 px-4 py-3 text-[12.5px] leading-relaxed text-ink-2">
          A credential must embed real proof. Add items to your{" "}
          <span className="font-medium text-ink">Evidence Vault</span> first, then
          come back to issue a credential backed by them.
        </p>
      )}

      {showForm && hasEvidence && (
        <form
          onSubmit={onSubmit}
          className="mb-6 space-y-4 rounded-[12px] border border-rule bg-paper p-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              value={skill}
              onChange={(e) => setSkill(e.target.value)}
              placeholder="Skill (e.g. React, Stakeholder Management)"
              className={FIELD_CLASS}
            />
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value as CredentialLevel)}
              className={FIELD_CLASS}
            >
              {LEVELS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="How you demonstrate this skill (optional)"
            rows={2}
            className={`${FIELD_CLASS} resize-y`}
          />
          <div>
            <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
              Backing evidence ({selectedEvidence.length} selected)
            </p>
            <div className="space-y-2">
              {(evidence ?? []).map((item: Evidence) => {
                const checked = selectedEvidence.includes(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => toggleEvidence(item.id)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-[9px] border px-3.5 py-2.5 text-left transition-colors duration-150",
                      checked
                        ? "border-green bg-green-soft"
                        : "border-rule bg-bg hover:border-rule-strong",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border text-[10px] font-bold text-bg",
                        checked ? "border-green bg-green" : "border-rule-strong bg-paper",
                      )}
                    >
                      {checked ? "✓" : ""}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-ink">
                        {item.title}
                      </span>
                      <span className="block text-[11.5px] text-ink-3">
                        {item.type}
                        {item.dateLabel ? ` · ${item.dateLabel}` : ""}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={
                !skill.trim() || selectedEvidence.length === 0 || issueMutation.isPending
              }
              className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
            >
              {issueMutation.isPending ? "Issuing…" : "Issue credential"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading your credentials…" />
      ) : !credentials || credentials.length === 0 ? (
        <EmptyState
          title="No credentials yet"
          description="Turn the proof in your Evidence Vault into a signed credential you can share with recruiters, clients, or your network."
        />
      ) : (
        <div className="space-y-4">
          {credentials.map((c: Credential) => {
            const revoked = c.status === "revoked";
            return (
              <article
                key={c.id}
                className={cn(
                  "flex flex-col gap-3 rounded-[12px] border bg-paper p-5",
                  revoked ? "border-rule opacity-70" : "border-rule",
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-green-2">
                      {LEVEL_LABEL[c.level]}
                    </span>
                    <h3 className="min-w-0 truncate font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
                      {c.skill}
                    </h3>
                    {revoked && (
                      <span className="rounded-[5px] bg-bg-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-destructive">
                        Revoked
                      </span>
                    )}
                  </div>
                </div>
                {c.summary && (
                  <p className="text-[13px] leading-relaxed text-ink-2">{c.summary}</p>
                )}
                <p className="text-[12px] text-ink-3">
                  {c.evidence.length} embedded evidence item
                  {c.evidence.length === 1 ? "" : "s"} · signature{" "}
                  <code className="rounded bg-bg-2 px-1 py-0.5 text-[10.5px] text-ink-2">
                    {c.signature.slice(0, 12)}…
                  </code>
                </p>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <a
                    href={c.verifyUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-rule-strong"
                  >
                    Open public page
                  </a>
                  <button
                    type="button"
                    onClick={() => copyLink(c.verifyUrl)}
                    className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-rule-strong"
                  >
                    Copy link
                  </button>
                  {!revoked && (
                    <button
                      type="button"
                      onClick={() => setPendingRevoke(c)}
                      className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                    >
                      Revoke
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setPendingDelete(c)}
                    className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                  >
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
        title="Revoke this credential?"
        description={
          pendingRevoke
            ? `Anyone opening the "${pendingRevoke.skill}" verification link will see it has been revoked. The link keeps working — it just reports the new status.`
            : undefined
        }
        confirmLabel="Revoke"
        destructive
        pending={revokeMutation.isPending}
        onConfirm={() => pendingRevoke && revokeMutation.mutate(pendingRevoke.id)}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this credential?"
        description={
          pendingDelete
            ? `"${pendingDelete.skill}" will be removed and its verification link will stop resolving.`
            : undefined
        }
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
      />
    </div>
  );
}
