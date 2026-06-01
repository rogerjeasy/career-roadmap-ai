"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { ROUTES } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";

interface ToggleProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}

function Toggle({ label, description, checked, onChange }: ToggleProps) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-rule py-4 last:border-b-0">
      <div className="min-w-0">
        <p className="text-[13.5px] font-medium text-ink">{label}</p>
        <p className="mt-0.5 text-[12.5px] text-ink-3">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-6 w-10 shrink-0 rounded-full transition-colors duration-150",
          checked ? "bg-green" : "bg-rule-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all duration-150",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [prefs, setPrefs] = useState({ weeklyDigest: true, milestoneAlerts: true, marketAlerts: false });
  const [confirmDelete, setConfirmDelete] = useState(false);

  const set = (key: keyof typeof prefs) => (v: boolean) => setPrefs((p) => ({ ...p, [key]: v }));

  return (
    <div className="mx-auto max-w-[760px] px-7 pb-24 pt-7">
      <PageHeader eyebrow="Account" title="Settings" description="Manage your account, preferences, and data." />

      {/* Account */}
      <section className="mb-6 rounded-[12px] border border-rule bg-paper p-6">
        <div className="flex items-center gap-3.5">
          <span className="flex h-12 w-12 items-center justify-center rounded-[12px] bg-green font-serif text-[16px] font-medium text-white">
            {(user?.displayName ?? user?.email ?? "U")[0]?.toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold text-ink">{user?.displayName ?? "Your account"}</p>
            <p className="truncate text-[12.5px] text-ink-3">{user?.email}</p>
          </div>
          <Link
            href={ROUTES.settingsProfile}
            className="ml-auto shrink-0 rounded-[7px] border border-rule-strong bg-paper px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
          >
            Edit profile
          </Link>
        </div>
      </section>

      {/* Quick links */}
      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <Link href={ROUTES.settingsProfile} className="rounded-[12px] border border-rule bg-paper p-5 transition-colors duration-150 hover:border-rule-strong">
          <p className="text-[14px] font-semibold text-ink">Profile</p>
          <p className="mt-1 text-[12.5px] text-ink-3">Your name, target role, and goal.</p>
        </Link>
        <Link href={ROUTES.settingsIntegrations} className="rounded-[12px] border border-rule bg-paper p-5 transition-colors duration-150 hover:border-rule-strong">
          <p className="text-[14px] font-semibold text-ink">Integrations</p>
          <p className="mt-1 text-[12.5px] text-ink-3">Connect LinkedIn, GitHub, and calendar.</p>
        </Link>
      </div>

      {/* Notifications */}
      <section className="mb-6 rounded-[12px] border border-rule bg-paper px-6 py-2">
        <h2 className="border-b border-rule py-4 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
          Notifications
        </h2>
        <Toggle label="Weekly digest" description="A Monday summary of your progress and focus." checked={prefs.weeklyDigest} onChange={set("weeklyDigest")} />
        <Toggle label="Milestone alerts" description="Get notified when a milestone is due or completed." checked={prefs.milestoneAlerts} onChange={set("milestoneAlerts")} />
        <Toggle label="Market alerts" description="New high-match roles in your target market." checked={prefs.marketAlerts} onChange={set("marketAlerts")} />
      </section>

      {/* Data & danger zone */}
      <section className="rounded-[12px] border border-rule bg-paper p-6">
        <h2 className="mb-1 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">Your data</h2>
        <p className="mb-4 text-[12.5px] text-ink-3">
          You control your data. Uploaded documents are hard-deleted; roadmaps and analyses are soft-deleted and recoverable.
        </p>
        <div className="flex flex-col gap-2.5 sm:flex-row">
          <button
            type="button"
            onClick={logout}
            className="rounded-[7px] border border-rule-strong bg-paper px-4 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
          >
            Sign out
          </button>
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="rounded-[7px] bg-destructive/10 px-4 py-2 text-[13px] font-medium text-destructive transition-colors duration-150 hover:bg-destructive/20"
          >
            Delete account
          </button>
        </div>
      </section>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete your account?"
        description="This permanently removes your profile, uploaded documents, roadmaps, and analyses. This action cannot be undone."
        confirmLabel="Delete everything"
        destructive
        onConfirm={() => setConfirmDelete(false)}
      />
    </div>
  );
}
