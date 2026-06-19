"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";
import { MentorDiscovery } from "@/components/mentorship/mentor-discovery";
import { MySessions } from "@/components/mentorship/my-sessions";
import { MentorProfileForm } from "@/components/mentorship/mentor-profile-form";
import { InsiderStories } from "@/components/mentorship/insider-stories";

type Tab = "discover" | "sessions" | "become" | "stories";

const TABS: { id: Tab; label: string }[] = [
  { id: "discover", label: "Find a mentor" },
  { id: "sessions", label: "My sessions" },
  { id: "become", label: "Become a mentor" },
  { id: "stories", label: "Insider stories" },
];

export default function MentorshipPage() {
  const [tab, setTab] = useState<Tab>("discover");

  return (
    <div className="mx-auto max-w-[900px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Community"
        title="Mentorship"
        description="Connect with mentors whose expertise maps to your goal, request a session, and learn from real insider stories of how others made the move you're aiming for."
      />

      <div className="mb-6 flex flex-wrap gap-1 rounded-[9px] border border-rule bg-bg-2 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "flex-1 whitespace-nowrap rounded-[7px] px-3 py-1.5 text-[12.5px] font-medium transition-colors duration-150",
              tab === t.id ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "discover" && <MentorDiscovery />}
      {tab === "sessions" && <MySessions />}
      {tab === "become" && <MentorProfileForm />}
      {tab === "stories" && <InsiderStories />}
    </div>
  );
}
