"use client";

import { Suspense, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { billingApi, type Subscription } from "@/lib/api/billing";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { ApiError } from "@/types/api.types";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { cn } from "@/lib/utils";

const PRO_PRICE = "$19";

const PRO_FEATURES = [
  "Unlimited roadmaps & phases",
  "Career Twin AI coach",
  "Opportunity radar & job matching",
  "Live market pulse · unlimited roles",
  "Weekly reviews & progress analytics",
  "Priority support",
];

const STATUS_LABEL: Record<Subscription["status"], string> = {
  none: "No active subscription",
  trialing: "Free trial",
  active: "Active",
  past_due: "Payment past due",
  canceled: "Canceled",
  incomplete: "Incomplete",
  unpaid: "Unpaid",
};

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? null
    : d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

function billingErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 503) return "Billing isn't enabled yet. Please try again later.";
    if (err.message) return err.message;
  }
  return fallback;
}

function BillingSettings() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const checkoutParam = searchParams.get("checkout");
  const handledParam = useRef(false);

  const { data: sub, isLoading } = useQuery({
    queryKey: QUERY_KEYS.subscription,
    queryFn: billingApi.getSubscription,
    staleTime: 30 * 1000,
  });

  // Surface the Checkout/Portal return outcome once, then clean the URL.
  useEffect(() => {
    if (!checkoutParam || handledParam.current) return;
    handledParam.current = true;
    if (checkoutParam === "success") {
      toast.success("You're on Pro — welcome aboard!");
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.subscription });
    } else if (checkoutParam === "cancelled") {
      toast.info("Checkout cancelled — no changes made.");
    }
    router.replace(ROUTES.settingsBilling);
  }, [checkoutParam, queryClient, router]);

  const checkoutMutation = useMutation({
    mutationFn: billingApi.startCheckout,
    onSuccess: (url) => {
      window.location.href = url;
    },
    onError: (err) =>
      toast.error(billingErrorMessage(err, "Couldn't start checkout. Please try again.")),
  });

  const portalMutation = useMutation({
    mutationFn: billingApi.openPortal,
    onSuccess: (url) => {
      window.location.href = url;
    },
    onError: (err) =>
      toast.error(billingErrorMessage(err, "Couldn't open the billing portal.")),
  });

  const isPro = sub?.plan === "pro";
  const redirecting = checkoutMutation.isPending || portalMutation.isPending;

  const periodEnd = formatDate(sub?.currentPeriodEnd ?? null);
  const trialEnd = formatDate(sub?.trialEnd ?? null);
  const statusDetail = !sub
    ? null
    : sub.cancelAtPeriodEnd && periodEnd
      ? `Your plan ends on ${periodEnd}.`
      : sub.status === "trialing" && trialEnd
        ? `Free trial ends ${trialEnd}.`
        : sub.status === "active" && periodEnd
          ? `Renews ${periodEnd}.`
          : null;

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
        title="Plan & billing"
        description="Manage your subscription, payment method, and invoices."
      />

      {isLoading || !sub ? (
        <LoadingSpinner fullPage label="Loading your plan…" />
      ) : (
        <div className="space-y-5">
          {/* Current plan */}
          <div className="rounded-[12px] border border-rule bg-paper p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                  Current plan
                </p>
                <h2 className="mt-1 font-serif text-[22px] font-medium tracking-[-0.01em] text-ink">
                  {isPro ? "Pro" : "Starter"}
                </h2>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-[5px] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.04em]",
                  isPro ? "bg-green-soft text-green-2" : "bg-bg-2 text-ink-2",
                )}
              >
                {STATUS_LABEL[sub.status]}
              </span>
            </div>
            {statusDetail && (
              <p className="mt-2 text-[13px] text-ink-2">{statusDetail}</p>
            )}
          </div>

          {/* Upgrade card (only when not Pro) */}
          {!isPro && (
            <div className="rounded-[12px] border border-rule bg-paper p-6">
              <div className="mb-4 flex items-baseline gap-2">
                <h3 className="font-serif text-[18px] font-medium tracking-[-0.01em] text-ink">
                  Upgrade to Pro
                </h3>
                <span className="text-[13px] text-ink-3">
                  {PRO_PRICE}/mo · 14-day free trial
                </span>
              </div>
              <ul className="mb-5 grid gap-2 sm:grid-cols-2">
                {PRO_FEATURES.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-[13px] text-ink-2">
                    <span className="mt-[3px] text-green" aria-hidden="true">
                      ✓
                    </span>
                    <span className="min-w-0">{f}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => checkoutMutation.mutate()}
                disabled={redirecting}
                className="inline-flex items-center justify-center rounded-[7px] bg-ink px-5 py-2.5 text-[13.5px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
              >
                {checkoutMutation.isPending ? "Redirecting…" : "Start 14-day free trial"}
              </button>
            </div>
          )}

          {/* Manage billing (when there's a Stripe customer) */}
          {sub.hasBillingAccount && (
            <div className="flex flex-col gap-3 rounded-[12px] border border-rule bg-paper p-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h3 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
                  Manage billing
                </h3>
                <p className="mt-1 text-[13px] text-ink-2">
                  Update your card, download invoices, or cancel — in Stripe&apos;s secure portal.
                </p>
              </div>
              <button
                type="button"
                onClick={() => portalMutation.mutate()}
                disabled={redirecting}
                className="shrink-0 rounded-[7px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-50"
              >
                {portalMutation.isPending ? "Opening…" : "Open billing portal"}
              </button>
            </div>
          )}

          {/* Teams */}
          <p className="text-[13px] text-ink-3">
            Need seats for a team or cohort?{" "}
            <Link
              href="/contact"
              className="font-medium text-terra transition-colors hover:text-terra-2"
            >
              Talk to sales →
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}

export default function BillingSettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-[680px] px-7 pb-24 pt-7">
          <LoadingSpinner fullPage label="Loading your plan…" />
        </div>
      }
    >
      <BillingSettings />
    </Suspense>
  );
}
