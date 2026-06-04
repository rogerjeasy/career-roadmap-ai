"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  integrationsApi,
  type IntegrationProvider,
  type IntegrationStatus,
} from "@/lib/api/integrations";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { formatDate } from "@/lib/date";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

export default function IntegrationsPage() {
  return (
    <Suspense fallback={<LoadingSpinner fullPage label="Loading integrations…" />}>
      <IntegrationsView />
    </Suspense>
  );
}

function IntegrationsView() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pending, setPending] = useState<IntegrationProvider | null>(null);

  const { data: integrations, isLoading } = useQuery({
    queryKey: QUERY_KEYS.integrations,
    queryFn: integrationsApi.list,
    staleTime: 30 * 1000,
  });

  // Surface the OAuth callback result (?provider=&status=) once, then clean the URL.
  useEffect(() => {
    const provider = searchParams.get("provider");
    const status = searchParams.get("status");
    if (!provider || !status) return;
    if (status === "connected") toast.success(`${provider} connected`);
    else if (status === "denied") toast.message(`${provider} connection cancelled`);
    else toast.error(`Couldn't connect ${provider}. Please try again.`);
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.integrations });
    router.replace(ROUTES.settings + "/integrations");
  }, [searchParams, queryClient, router]);

  const disconnectMutation = useMutation({
    mutationFn: integrationsApi.disconnect,
    onSuccess: (_data, provider) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.integrations });
      toast.message(`${provider} disconnected`);
    },
    onError: () => toast.error("Couldn't disconnect. Please try again."),
  });

  const onConnect = async (provider: IntegrationProvider) => {
    setPending(provider);
    try {
      const url = await integrationsApi.authorize(provider);
      window.location.assign(url); // hand off to the provider's consent screen
    } catch {
      toast.error("Couldn't start the connection. Please try again.");
      setPending(null);
    }
  };

  return (
    <div className="mx-auto max-w-[680px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.settings}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Settings
      </Link>
      <PageHeader
        eyebrow="Account"
        title="Integrations"
        description="Connect external accounts to enrich your roadmap. Connections are explicit and revocable at any time."
      />

      {isLoading ? (
        <LoadingSpinner fullPage label="Loading integrations…" />
      ) : (
        <ul className="space-y-3">
          {(integrations ?? []).map((i) => (
            <IntegrationRow
              key={i.provider}
              integration={i}
              connecting={pending === i.provider}
              disconnecting={
                disconnectMutation.isPending && disconnectMutation.variables === i.provider
              }
              onConnect={() => onConnect(i.provider)}
              onDisconnect={() => disconnectMutation.mutate(i.provider)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface IntegrationRowProps {
  integration: IntegrationStatus;
  connecting: boolean;
  disconnecting: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}

function IntegrationRow({
  integration,
  connecting,
  disconnecting,
  onConnect,
  onDisconnect,
}: IntegrationRowProps) {
  const { name, description, consentNote, available, connected, accountLabel, connectedAt } =
    integration;

  return (
    <li className="rounded-[12px] border border-rule bg-paper p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-semibold text-ink">{name}</h3>
            {connected && (
              <span className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-green-2">
                Connected
              </span>
            )}
            {!available && !connected && (
              <span className="rounded-[5px] bg-bg-3 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-ink-3">
                Not yet available
              </span>
            )}
          </div>
          <p className="mt-1 text-[13px] text-ink-2">{description}</p>
          {connected && accountLabel && (
            <p className="mt-1.5 text-[12px] text-ink-2">
              Connected as <span className="font-medium text-ink">{accountLabel}</span>
              {connectedAt ? ` · ${formatDate(connectedAt, "MMM d, yyyy")}` : ""}
            </p>
          )}
          <p className="mt-2 text-[11.5px] leading-snug text-ink-3">{consentNote}</p>
          {!available && !connected && (
            <p className="mt-1 text-[11.5px] leading-snug text-ink-3">
              An administrator needs to configure {name} OAuth credentials before this can be connected.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={connected ? onDisconnect : onConnect}
          disabled={(!available && !connected) || connecting || disconnecting}
          className={cn(
            "shrink-0 rounded-[7px] px-4 py-2 text-[13px] font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
            connected
              ? "border border-rule-strong bg-paper text-ink-2 hover:bg-bg-2"
              : "bg-ink text-bg hover:bg-green-2",
          )}
        >
          {connected
            ? disconnecting
              ? "Disconnecting…"
              : "Disconnect"
            : connecting
              ? "Connecting…"
              : "Connect"}
        </button>
      </div>
    </li>
  );
}
