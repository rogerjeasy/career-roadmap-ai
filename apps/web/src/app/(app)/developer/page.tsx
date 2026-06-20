"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiKeysApi, type ApiKey, type ApiKeyCreated } from "@/lib/api/api-keys";
import { QUERY_KEYS, API_URL } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { WebhooksPanel } from "@/components/developer/webhooks-panel";
import { formatRelative } from "@/lib/date";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export default function DeveloperPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ApiKey | null>(null);

  const { data: keys, isLoading } = useQuery({
    queryKey: QUERY_KEYS.apiKeys,
    queryFn: apiKeysApi.list,
    staleTime: 30 * 1000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.apiKeys });

  const createMutation = useMutation({
    mutationFn: (n: string) => apiKeysApi.create(n),
    onSuccess: (data) => {
      invalidate();
      setCreated(data);
      setName("");
      toast.success("API key created — copy it now");
    },
    onError: () => toast.error("Couldn't create a key."),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => apiKeysApi.revoke(id),
    onSuccess: () => {
      invalidate();
      toast.success("Key revoked");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiKeysApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Key deleted");
      setPendingDelete(null);
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createMutation.mutate(name.trim());
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied");
    } catch {
      toast.error("Couldn't copy");
    }
  };

  return (
    <div className="mx-auto max-w-[820px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Platform"
        title="Developer API"
        description="Mint personal API keys to read your own data programmatically. Keys are shown once and stored only as a hash — treat them like passwords."
      />

      <form onSubmit={onSubmit} className="mb-6 flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Key name (e.g. My script)"
          className={FIELD_CLASS}
        />
        <button
          type="submit"
          disabled={!name.trim() || createMutation.isPending}
          className="shrink-0 rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {createMutation.isPending ? "Creating…" : "Create key"}
        </button>
      </form>

      {created && (
        <div className="mb-6 rounded-[12px] border border-green bg-paper p-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-green-2">
            Copy your key now — it won&apos;t be shown again
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-[8px] bg-bg-2 px-3 py-2 text-[12.5px] text-ink">
              {created.key}
            </code>
            <button
              type="button"
              onClick={() => copy(created.key)}
              className="shrink-0 rounded-[7px] bg-ink px-3 py-2 text-[12px] font-medium text-bg transition-colors hover:bg-green-2"
            >
              Copy
            </button>
          </div>
          <button
            type="button"
            onClick={() => setCreated(null)}
            className="mt-2 text-[12px] font-medium text-ink-3 transition-colors hover:text-ink"
          >
            I&apos;ve saved it
          </button>
        </div>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading keys…" />
      ) : !keys || keys.length === 0 ? (
        <EmptyState
          title="No API keys yet"
          description="Create a key above to start using the public API."
        />
      ) : (
        <div className="space-y-2">
          {keys.map((k: ApiKey) => (
            <div
              key={k.id}
              className="flex items-center justify-between gap-3 rounded-[10px] border border-rule bg-paper px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[13px] font-medium text-ink">{k.name}</span>
                  {k.revoked && (
                    <span className="shrink-0 rounded-[4px] bg-terra-soft px-1.5 py-0.5 text-[10px] font-semibold text-terra-2">
                      revoked
                    </span>
                  )}
                </div>
                <p className="text-[11.5px] text-ink-3">
                  <code>{k.prefix}…{k.last4}</code>
                  {k.lastUsedAt ? ` · used ${formatRelative(k.lastUsedAt)}` : " · never used"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {!k.revoked && (
                  <button
                    type="button"
                    onClick={() => revokeMutation.mutate(k.id)}
                    className="text-[12px] font-medium text-ink-3 transition-colors hover:text-terra-2"
                  >
                    Revoke
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setPendingDelete(k)}
                  className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-8 rounded-[12px] border border-rule bg-paper p-5">
        <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          Quick start
        </p>
        <pre className="mt-2 overflow-x-auto rounded-[8px] bg-bg-2 px-3.5 py-3 text-[12px] leading-relaxed text-ink-2">
          <code>{`curl ${API_URL}/api/v1/public/me \\
  -H "X-API-Key: YOUR_KEY"

curl ${API_URL}/api/v1/public/roadmap \\
  -H "X-API-Key: YOUR_KEY"`}</code>
        </pre>
      </div>

      <WebhooksPanel />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this key?"
        description={
          pendingDelete
            ? `"${pendingDelete.name}" will stop working immediately and permanently.`
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
