"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { progressApi } from "@/lib/api/progress";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import {
  WeeklyScorecardForm,
  type WeeklyScorecardValues,
} from "@/components/progress/weekly-scorecard-form";

export default function WeeklyReviewPage() {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState<WeeklyScorecardValues | null>(null);

  const mutation = useMutation({
    mutationFn: progressApi.createReview,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.weeklyReviews });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.health });
      setSaved({
        energy: variables.energy,
        focus: variables.focus,
        wins: variables.wins ?? "",
        blockers: variables.blockers ?? "",
        hoursInvested: variables.hoursInvested ?? 0,
        milestonesClosed: variables.milestonesClosed ?? 0,
      });
      toast.success("Weekly review saved");
    },
    onError: () => toast.error("Couldn't save your review. Please try again."),
  });

  const onSubmit = (values: WeeklyScorecardValues) => {
    mutation.mutate({
      energy: values.energy,
      focus: values.focus,
      wins: values.wins,
      blockers: values.blockers,
      hoursInvested: values.hoursInvested,
      milestonesClosed: values.milestonesClosed,
    });
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
