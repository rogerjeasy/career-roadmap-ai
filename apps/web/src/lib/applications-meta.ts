import type {
  ApplicationOutcome,
  ApplicationStatus,
} from "@/lib/api/applications";

/** Ordered pipeline stages, left → right on the board. */
export const STAGES: readonly ApplicationStatus[] = [
  "saved",
  "applied",
  "screening",
  "interview",
  "offer",
  "closed",
] as const;

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  closed: "Closed",
};

/** Column header accent + count chip per stage. */
export const STATUS_TONE: Record<ApplicationStatus, string> = {
  saved: "bg-bg-2 text-ink-2",
  applied: "bg-green-faint text-green-2",
  screening: "bg-green-soft text-green-2",
  interview: "bg-gold-soft text-ink-2",
  offer: "bg-green text-bg",
  closed: "bg-bg-3 text-ink-3",
};

export const OUTCOME_LABEL: Record<ApplicationOutcome, string> = {
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const OUTCOME_TONE: Record<ApplicationOutcome, string> = {
  accepted: "bg-green text-bg",
  rejected: "bg-terra-soft text-terra-2",
  withdrawn: "bg-bg-2 text-ink-3",
};

export const OUTCOMES: readonly ApplicationOutcome[] = [
  "accepted",
  "rejected",
  "withdrawn",
] as const;
