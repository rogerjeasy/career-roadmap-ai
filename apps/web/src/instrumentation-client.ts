/**
 * Client-side instrumentation hook (Next.js 16 file convention).
 *
 * Runs after the HTML document loads but before React hydration, so it captures
 * the earliest client lifecycle errors. DSN-gated: when `NEXT_PUBLIC_SENTRY_DSN`
 * is unset, `Sentry.init` never runs and every capture downstream is a no-op.
 *
 * Session Replay is wired error-only (`replaysSessionSampleRate: 0`) to keep the
 * init lightweight — Next warns when client instrumentation exceeds ~16 ms.
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: Number(
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
    ),
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 1.0,
    integrations: [Sentry.replayIntegration()],
    sendDefaultPii: false,
  });
}

// Adds navigation breadcrumbs + ties App Router transitions to traces.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
