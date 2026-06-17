import { apiClient } from "./client";

export type BillingPlan = "free" | "pro" | "teams";
export type SubscriptionStatus =
  | "none"
  | "trialing"
  | "active"
  | "past_due"
  | "canceled"
  | "incomplete"
  | "unpaid";

export interface Subscription {
  plan: BillingPlan;
  status: SubscriptionStatus;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  trialEnd: string | null;
  hasBillingAccount: boolean;
}

export const billingApi = {
  async getSubscription(): Promise<Subscription> {
    const { data } = await apiClient.get<Subscription>("/api/v1/billing/subscription");
    return data;
  },

  /** Returns a Stripe Checkout URL to redirect the browser to. */
  async startCheckout(): Promise<string> {
    const { data } = await apiClient.post<{ url: string }>("/api/v1/billing/checkout");
    return data.url;
  },

  /** Returns a Stripe Billing Portal URL to redirect the browser to. */
  async openPortal(): Promise<string> {
    const { data } = await apiClient.post<{ url: string }>("/api/v1/billing/portal");
    return data.url;
  },
};
