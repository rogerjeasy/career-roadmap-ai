import { format, formatDistanceToNow, parseISO } from "date-fns";

function toDate(value: string | number | Date): Date {
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value);
  return parseISO(value);
}

/** "3 hours ago", "in 2 days", etc. */
export function formatRelative(value: string | number | Date): string {
  try {
    return formatDistanceToNow(toDate(value), { addSuffix: true });
  } catch {
    return "";
  }
}

/** "Jun 1, 2026" by default; pass a date-fns pattern to override. */
export function formatDate(value: string | number | Date, pattern = "MMM d, yyyy"): string {
  try {
    return format(toDate(value), pattern);
  } catch {
    return "";
  }
}

/** "Jun 1, 2026 · 14:30" */
export function formatDateTime(value: string | number | Date): string {
  return formatDate(value, "MMM d, yyyy · HH:mm");
}
