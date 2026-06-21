"use client";

/**
 * Root error boundary — catches errors thrown in the root layout itself, which
 * the per-route `error.tsx` cannot reach. Must render its own <html>/<body>
 * because it replaces the root layout when it activates. Reports to Sentry
 * (no-op when the DSN is unset) before rendering a minimal recovery screen.
 */
import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="bg-bg text-ink">
        <div className="flex min-h-screen flex-col items-center justify-center px-6 py-20 text-center">
          <h1 className="mb-3 font-serif text-2xl font-medium tracking-[-0.02em] sm:text-3xl">
            Something went wrong
          </h1>
          <p className="mb-8 max-w-sm text-[15px] leading-relaxed text-ink-2">
            An unexpected error occurred. Our team has been notified.
          </p>
          {error.digest && (
            <p className="mb-8 font-mono text-[11px] tracking-widest text-ink-3">
              ref: {error.digest}
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-medium text-bg transition-colors hover:bg-green-2"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
