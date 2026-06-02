"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { progressApi } from "@/lib/api/progress";
import { scheduleApi } from "@/lib/api/schedule";
import { formatDate } from "@/lib/date";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { CareerHealthScore } from "@/components/progress/career-health-score";
import { HabitCompletionChart, type HabitWeek } from "@/components/progress/habit-completion-chart";
import { MetricChart, type MetricPoint } from "@/components/progress/metric-chart";

function EmptyCard({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[12px] border border-dashed border-rule bg-paper px-6 py-10 text-center">
      <p className="mb-1 text-[13px] font-medium text-ink-2">{title}</p>
      <p className="max-w-[280px] text-[12px] text-ink-3">{body}</p>
    </div>
  );
}

export default function ProgressPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: QUERY_KEYS.health,
    queryFn: progressApi.getHealth,
    staleTime: 60 * 1000,
  });

  const { data: habits, isLoading: habitsLoading } = useQuery({
    queryKey: QUERY_KEYS.habits,
    queryFn: scheduleApi.listHabits,
    staleTime: 60 * 1000,
  });

  const { data: reviews, isLoading: reviewsLoading } = useQuery({
    queryKey: QUERY_KEYS.weeklyReviews,
    queryFn: () => progressApi.listReviews(12),
    staleTime: 60 * 1000,
  });

  const hasHealth = Boolean(health && health.updatedAt);

  const habitWeeks: HabitWeek[] = (habits ?? [])
    .filter((h) => h.weekCompletions.length === 7)
    .map((h) => ({ habit: h.label, days: h.weekCompletions }));

  // Reviews arrive newest-first; charts read oldest → newest.
  const orderedReviews = [...(reviews ?? [])].reverse();
  const reviewLabel = (weekOf: string | null, createdAt: string) =>
    weekOf?.trim() ? weekOf : formatDate(createdAt, "MMM d");

  const hoursPoints: MetricPoint[] = orderedReviews.map((r) => ({
    label: reviewLabel(r.weekOf, r.createdAt),
    value: r.hoursInvested,
  }));
  const milestonePoints: MetricPoint[] = orderedReviews.map((r) => ({
    label: reviewLabel(r.weekOf, r.createdAt),
    value: r.milestonesClosed,
  }));

  return (
    <div className="mx-auto max-w-[1100px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Momentum"
        title="Progress"
        description="How your career health, habits, and effort are trending over time."
        actions={
          <Link
            href={ROUTES.progress + "/review"}
            className="inline-flex items-center rounded-[7px] bg-ink px-3.5 py-2 text-[13px] font-medium text-bg transition-colors duration-150 hover:bg-green-2"
          >
            Weekly review
          </Link>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
        {healthLoading ? (
          <EmptyCard title="Loading…" body="Fetching your latest career-health snapshot." />
        ) : hasHealth ? (
          <CareerHealthScore
            score={health!.score}
            delta={health!.delta ?? undefined}
            signals={health!.signals}
          />
        ) : (
          <EmptyCard
            title="No health snapshot yet"
            body="Your career-health score and signals appear here once your roadmap and reviews give the coach enough to assess."
          />
        )}

        <div className="flex flex-col gap-5">
          {habitsLoading ? (
            <EmptyCard title="Loading…" body="Fetching this week's habit completions." />
          ) : habitWeeks.length > 0 ? (
            <HabitCompletionChart weeks={habitWeeks} />
          ) : (
            <EmptyCard
              title="No habits to track yet"
              body="Add habits on your schedule and check them off — this week's completion shows up here."
            />
          )}

          <div className="grid gap-5 sm:grid-cols-2">
            {reviewsLoading ? (
              <EmptyCard title="Loading…" body="Fetching your weekly reviews." />
            ) : orderedReviews.length > 0 ? (
              <>
                <MetricChart title="Hours invested" unit="h" points={hoursPoints} tone="green" />
                <MetricChart title="Milestones closed" points={milestonePoints} tone="terra" />
              </>
            ) : (
              <EmptyCard
                title="No weekly reviews yet"
                body="File a weekly review to start tracking hours invested and milestones closed over time."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
