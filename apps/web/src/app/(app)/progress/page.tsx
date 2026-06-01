"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { CareerHealthScore } from "@/components/progress/career-health-score";
import { HabitCompletionChart } from "@/components/progress/habit-completion-chart";
import { MetricChart } from "@/components/progress/metric-chart";

const SIGNALS = [
  { label: "Roadmap progress", score: 84 },
  { label: "Skill readiness", score: 71 },
  { label: "Portfolio strength", score: 62 },
  { label: "Market alignment", score: 88 },
  { label: "Network activity", score: 42 },
];

const HABITS = [
  { habit: "Morning study block", days: [true, true, true, false, true, false, false] },
  { habit: "Ship something small", days: [true, false, true, true, true, false, false] },
  { habit: "One outreach message", days: [false, true, false, true, false, false, false] },
];

const HOURS = [
  { label: "W1", value: 8 },
  { label: "W2", value: 11 },
  { label: "W3", value: 9 },
  { label: "W4", value: 12 },
  { label: "W5", value: 10 },
  { label: "W6", value: 13 },
];

const MILESTONES = [
  { label: "W1", value: 1 },
  { label: "W2", value: 2 },
  { label: "W3", value: 2 },
  { label: "W4", value: 4 },
  { label: "W5", value: 5 },
  { label: "W6", value: 7 },
];

export default function ProgressPage() {
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
        <CareerHealthScore score={76} delta={8} signals={SIGNALS} />

        <div className="flex flex-col gap-5">
          <HabitCompletionChart weeks={HABITS} />
          <div className="grid gap-5 sm:grid-cols-2">
            <MetricChart title="Hours invested" unit="h" points={HOURS} tone="green" />
            <MetricChart title="Milestones closed" points={MILESTONES} tone="terra" />
          </div>
        </div>
      </div>
    </div>
  );
}
