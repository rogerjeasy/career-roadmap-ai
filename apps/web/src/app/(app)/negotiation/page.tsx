"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";
import { OfferAnalyzer } from "@/components/negotiation/offer-analyzer";
import { NegotiationRoleplay } from "@/components/negotiation/roleplay";

type Tab = "analyze" | "roleplay";

export default function NegotiationPage() {
  const [tab, setTab] = useState<Tab>("analyze");

  return (
    <div className="mx-auto max-w-[860px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Offers"
        title="Negotiation Coach"
        description="Benchmark an offer against the market, draft a defensible counter, and rehearse the conversation with an AI recruiter before the real one."
      />

      <div className="mb-6 flex gap-1 rounded-[9px] border border-rule bg-bg-2 p-1">
        {(["analyze", "roleplay"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-150",
              tab === t ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
            )}
          >
            {t === "analyze" ? "Benchmark & counter" : "Roleplay"}
          </button>
        ))}
      </div>

      {tab === "analyze" ? <OfferAnalyzer /> : <NegotiationRoleplay />}
    </div>
  );
}
