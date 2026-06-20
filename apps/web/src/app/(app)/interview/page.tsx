"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";
import { QuestionBank } from "@/components/interview/question-bank";
import { MockInterview } from "@/components/interview/mock-interview";

type Tab = "mock" | "questions";

export default function InterviewPage() {
  const [tab, setTab] = useState<Tab>("mock");

  return (
    <div className="mx-auto max-w-[860px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Practice"
        title="Interview Prep"
        description="Rehearse with an AI interviewer that scores every answer, or generate a tailored question bank for a specific role and company."
      />

      <div className="mb-6 flex gap-1 rounded-[9px] border border-rule bg-bg-2 p-1">
        {(["mock", "questions"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-150",
              tab === t ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
            )}
          >
            {t === "mock" ? "Mock interview" : "Question bank"}
          </button>
        ))}
      </div>

      {tab === "mock" ? <MockInterview /> : <QuestionBank />}
    </div>
  );
}
