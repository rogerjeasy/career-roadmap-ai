"use client";

import Link from "next/link";
import { useCvStore } from "@/store/cv.store";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { CvResults } from "@/components/cv-analysis/cv-results";

export default function CvResultsPage() {
  const analysis = useCvStore((s) => s.analysis);

  return (
    <div className="mx-auto max-w-[1000px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.cvAnalysis}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← CV & Profile
      </Link>
      <PageHeader eyebrow="Your profile" title="Analysis results" />

      {analysis ? (
        <CvResults analysis={analysis} />
      ) : (
        <EmptyState
          title="No analysis yet"
          description="Upload a CV to see your extracted profile and readiness score."
          action={
            <Link
              href={ROUTES.cvAnalysis}
              className="inline-flex items-center rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
            >
              Upload CV
            </Link>
          }
        />
      )}
    </div>
  );
}
