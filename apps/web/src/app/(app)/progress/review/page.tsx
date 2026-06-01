"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import {
  WeeklyScorecardForm,
  type WeeklyScorecardValues,
} from "@/components/progress/weekly-scorecard-form";

export default function WeeklyReviewPage() {
  const [saved, setSaved] = useState<WeeklyScorecardValues | null>(null);

  const onSubmit = (values: WeeklyScorecardValues) => {
    setSaved(values);
    toast.success("Weekly review saved");
  };

  return (
    <div className="mx-auto max-w-[680px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.progress}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Progress
      </Link>
      <PageHeader
        eyebrow="Momentum"
        title="Weekly review"
        description="A two-minute reflection keeps your roadmap honest. Your coach uses these to adjust your plan."
      />

      <WeeklyScorecardForm onSubmit={onSubmit} />

      {saved && (
        <p className="mt-4 rounded-[8px] bg-green-faint px-4 py-3 text-[13px] text-green-2">
          Saved · energy {saved.energy}/5 · focus {saved.focus}/5. Keep the streak going next week.
        </p>
      )}
    </div>
  );
}
