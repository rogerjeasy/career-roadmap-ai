"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";

interface Integration {
  id: string;
  name: string;
  description: string;
  consentNote: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "linkedin",
    name: "LinkedIn",
    description: "Import your profile and surface relevant connections.",
    consentNote: "We read your profile and connections. We never post on your behalf.",
  },
  {
    id: "github",
    name: "GitHub",
    description: "Use your repositories as portfolio evidence.",
    consentNote: "We read public repository metadata only.",
  },
  {
    id: "calendar",
    name: "Calendar",
    description: "Let your coach schedule study blocks and reviews.",
    consentNote: "Calendar writes require a confirmation step before any event is created.",
  },
];

export default function IntegrationsPage() {
  const [connected, setConnected] = useState<Record<string, boolean>>({});

  const toggle = (id: string, name: string) => {
    setConnected((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      if (next[id]) toast.success(`${name} connected`);
      else toast.message(`${name} disconnected`);
      return next;
    });
  };

  return (
    <div className="mx-auto max-w-[680px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.settings}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Settings
      </Link>
      <PageHeader
        eyebrow="Account"
        title="Integrations"
        description="Connect external accounts to enrich your roadmap. Connections are explicit and revocable at any time."
      />

      <ul className="space-y-3">
        {INTEGRATIONS.map((i) => {
          const isConnected = Boolean(connected[i.id]);
          return (
            <li key={i.id} className="rounded-[12px] border border-rule bg-paper p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-[14px] font-semibold text-ink">{i.name}</h3>
                    {isConnected && (
                      <span className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.04em] text-green-2">
                        Connected
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[13px] text-ink-2">{i.description}</p>
                  <p className="mt-2 text-[11.5px] leading-snug text-ink-3">{i.consentNote}</p>
                </div>
                <button
                  type="button"
                  onClick={() => toggle(i.id, i.name)}
                  className={cn(
                    "shrink-0 rounded-[7px] px-4 py-2 text-[13px] font-medium transition-colors duration-150",
                    isConnected
                      ? "border border-rule-strong bg-paper text-ink-2 hover:bg-bg-2"
                      : "bg-ink text-bg hover:bg-green-2",
                  )}
                >
                  {isConnected ? "Disconnect" : "Connect"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
