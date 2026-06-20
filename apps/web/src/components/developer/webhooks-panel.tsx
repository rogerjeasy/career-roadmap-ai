"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { webhooksApi, type Webhook } from "@/lib/api/webhooks";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

export interface WebhooksPanelProps {
  className?: string;
}

export function WebhooksPanel(_props: WebhooksPanelProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState<string | null>(null);

  const { data: hooks, isLoading } = useQuery({
    queryKey: QUERY_KEYS.webhooks,
    queryFn: webhooksApi.list,
    staleTime: 30 * 1000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.webhooks });

  const createMutation = useMutation({
    mutationFn: () => webhooksApi.create(url.trim(), ["*"]),
    onSuccess: (data) => {
      invalidate();
      setSecret(data.secret);
      setUrl("");
      toast.success("Webhook registered — copy your signing secret");
    },
    onError: () => toast.error("Couldn't register that URL (must be a valid https URL)."),
  });

  const pingMutation = useMutation({
    mutationFn: (id: string) => webhooksApi.ping(id),
    onSuccess: (res) => {
      invalidate();
      if (res.delivered) toast.success(`Delivered (HTTP ${res.status})`);
      else toast.error(res.detail || `Endpoint returned ${res.status ?? "no response"}`);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => webhooksApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Webhook removed");
    },
  });

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied");
    } catch {
      toast.error("Couldn't copy");
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    createMutation.mutate();
  };

  return (
    <section className="mt-8 rounded-[12px] border border-rule bg-paper p-5">
      <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">Webhooks</h2>
      <p className="text-[12.5px] text-ink-3">
        Get a signed POST when events happen on your account. Verify with the{" "}
        <code className="rounded bg-bg-2 px-1 py-0.5 text-[11px]">X-CRA-Signature</code> header.
      </p>

      <form onSubmit={onSubmit} className="mt-4 flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://your-endpoint.example.com/hook"
          className="w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none"
        />
        <button
          type="submit"
          disabled={!url.trim() || createMutation.isPending}
          className="shrink-0 rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          Add
        </button>
      </form>

      {secret && (
        <div className="mt-3 rounded-[10px] border border-green bg-green-soft px-3.5 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-green-2">
            Signing secret (shown once)
          </p>
          <div className="mt-1.5 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate text-[12px] text-ink">{secret}</code>
            <button
              type="button"
              onClick={() => copy(secret)}
              className="shrink-0 rounded-[6px] bg-ink px-2.5 py-1 text-[11px] font-medium text-bg"
            >
              Copy
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="mt-4">
          <LoadingSpinner label="Loading webhooks…" />
        </div>
      ) : hooks && hooks.length > 0 ? (
        <ul className="mt-4 space-y-2">
          {hooks.map((h: Webhook) => (
            <li
              key={h.id}
              className="flex items-center justify-between gap-3 rounded-[9px] border border-rule bg-bg px-3.5 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-ink">{h.url}</p>
                <p className="text-[11.5px] text-ink-3">
                  {h.events.join(", ")}
                  {h.lastStatus !== null ? ` · last ${h.lastStatus}` : ""}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => pingMutation.mutate(h.id)}
                  disabled={pingMutation.isPending}
                  className="text-[12px] font-medium text-ink-2 transition-colors hover:text-ink disabled:opacity-50"
                >
                  Ping
                </button>
                <button
                  type="button"
                  onClick={() => removeMutation.mutate(h.id)}
                  className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-[12.5px] text-ink-3">No webhooks registered yet.</p>
      )}
    </section>
  );
}
