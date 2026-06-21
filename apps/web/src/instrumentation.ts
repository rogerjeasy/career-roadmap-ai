/**
 * Server + edge runtime instrumentation hook (Next.js 16 file convention).
 *
 * `register()` runs once per server instance before any request is handled.
 * Sentry is DSN-gated: when `NEXT_PUBLIC_SENTRY_DSN` is unset the init is
 * skipped entirely, so local/dev runs and unconfigured deploys are a no-op —
 * mirroring the backend's `setup_sentry()` behaviour.
 *
 * `onRequestError` forwards server-side errors (Server Components, Route
 * Handlers, Server Actions) to Sentry. It is safe to export unconditionally:
 * if `Sentry.init` never ran, the capture is a no-op.
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

const tracesSampleRate = Number(
  process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
);

export async function register(): Promise<void> {
  if (!dsn) return;

  // instrumentation.ts loads in both the Node.js and Edge runtimes.
  if (
    process.env.NEXT_RUNTIME === "nodejs" ||
    process.env.NEXT_RUNTIME === "edge"
  ) {
    Sentry.init({
      dsn,
      environment: process.env.NODE_ENV,
      tracesSampleRate,
      // Only send PII (request bodies, headers) after a privacy review.
      sendDefaultPii: false,
    });
  }
}

export const onRequestError = Sentry.captureRequestError;
