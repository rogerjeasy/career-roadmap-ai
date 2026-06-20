"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { pushApi } from "@/lib/api/push";
import { QUERY_KEYS } from "@/lib/constants";
import {
  pushSupported,
  subscribeToPush,
  unsubscribeFromPush,
  getCurrentSubscription,
} from "@/lib/push";

export interface PushNotificationsProps {
  className?: string;
}

export function PushNotifications(_props: PushNotificationsProps): React.ReactElement {
  const supported = pushSupported();
  const [subscribed, setSubscribed] = useState(false);
  // Only "checking" when push is supported (otherwise there's nothing to check).
  const [checking, setChecking] = useState(supported);

  const { data: config } = useQuery({
    queryKey: QUERY_KEYS.pushConfig,
    queryFn: pushApi.config,
    enabled: supported,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!supported) return;
    let active = true;
    getCurrentSubscription()
      .then((sub) => active && setSubscribed(Boolean(sub)))
      .finally(() => active && setChecking(false));
    return () => {
      active = false;
    };
  }, [supported]);

  const enableMutation = useMutation({
    mutationFn: async () => {
      if (!config?.publicKey) throw new Error("not-configured");
      const sub = await subscribeToPush(config.publicKey);
      await pushApi.subscribe({
        endpoint: sub.endpoint ?? "",
        keys: { p256dh: sub.keys?.p256dh ?? "", auth: sub.keys?.auth ?? "" },
        expirationTime: sub.expirationTime ?? null,
      });
    },
    onSuccess: () => {
      setSubscribed(true);
      toast.success("Notifications enabled on this device");
    },
    onError: (e: Error) =>
      toast.error(
        e.message === "not-configured"
          ? "Push isn't configured on the server yet."
          : "Couldn't enable notifications.",
      ),
  });

  const disableMutation = useMutation({
    mutationFn: async () => {
      const endpoint = await unsubscribeFromPush();
      if (endpoint) await pushApi.unsubscribe(endpoint);
    },
    onSuccess: () => {
      setSubscribed(false);
      toast.success("Notifications disabled on this device");
    },
    onError: () => toast.error("Couldn't disable notifications."),
  });

  const testMutation = useMutation({
    mutationFn: pushApi.test,
    onSuccess: (res) => {
      if (res.sent > 0) toast.success("Test notification sent");
      else toast.message(res.detail || "No active devices to notify.");
    },
    onError: () => toast.error("Couldn't send a test."),
  });

  if (!supported) {
    return (
      <div className="flex items-center justify-between gap-4 border-b border-rule py-4 last:border-0">
        <div className="min-w-0">
          <p className="text-[13.5px] font-medium text-ink">Push notifications</p>
          <p className="mt-0.5 text-[12.5px] text-ink-3">
            This browser doesn&apos;t support push notifications.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 border-b border-rule py-4 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-[13.5px] font-medium text-ink">Push notifications</p>
        <p className="mt-0.5 text-[12.5px] text-ink-3">
          Daily check-in nudges, cohort reminders, and application follow-ups on this device.
          {config && !config.enabled && " (server not configured yet)"}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {subscribed && (
          <button
            type="button"
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending}
            className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink-2 transition-colors hover:border-rule-strong disabled:opacity-50"
          >
            Send test
          </button>
        )}
        <button
          type="button"
          onClick={() => (subscribed ? disableMutation.mutate() : enableMutation.mutate())}
          disabled={checking || enableMutation.isPending || disableMutation.isPending}
          className="rounded-[7px] bg-ink px-3.5 py-1.5 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {subscribed ? "Disable" : "Enable"}
        </button>
      </div>
    </div>
  );
}
