"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { privacyApi } from "@/lib/api/privacy";
import { ROUTES } from "@/lib/constants";
import { useAuth } from "@/hooks/use-auth";
import { PageHeader } from "@/components/shared/page-header";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

export default function PrivacySettingsPage() {
  const { logout } = useAuth();
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const exportMutation = useMutation({
    mutationFn: privacyApi.export,
    onSuccess: (bundle) => {
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `career-roadmap-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success("Your data export downloaded");
    },
    onError: () => toast.error("Couldn't export your data. Please try again."),
  });

  const purgeMutation = useMutation({
    mutationFn: privacyApi.purge,
    onSuccess: (res) => {
      toast.success(`Erased ${res.removed} record${res.removed === 1 ? "" : "s"}`);
      setConfirmPurge(false);
    },
    onError: () => toast.error("Couldn't erase your data."),
  });

  const deleteMutation = useMutation({
    mutationFn: privacyApi.deleteAccount,
    onSuccess: async () => {
      toast.success("Account deleted");
      setConfirmDelete(false);
      await logout();
    },
    onError: () => toast.error("Couldn't delete your account."),
  });

  return (
    <div className="mx-auto max-w-[680px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.settings}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Settings
      </Link>
      <PageHeader
        eyebrow="Your data"
        title="Privacy &amp; data"
        description="You own your data. Download a full copy anytime, erase your activity, or permanently close your account."
      />

      <section className="mb-5 rounded-[12px] border border-rule bg-paper p-6">
        <h2 className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
          Export your data
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
          Download everything you&apos;ve created — applications, evidence, roadmap
          snapshots, credentials, and more — as a single JSON file.
        </p>
        <button
          type="button"
          onClick={() => exportMutation.mutate()}
          disabled={exportMutation.isPending}
          className="mt-4 rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {exportMutation.isPending ? "Preparing…" : "Download my data"}
        </button>
      </section>

      <section className="rounded-[12px] border border-terra/50 bg-paper p-6">
        <h2 className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">
          Danger zone
        </h2>
        <div className="mt-3 flex flex-col gap-3 border-t border-rule pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-[13.5px] font-medium text-ink">Erase my data</p>
            <p className="text-[12.5px] text-ink-3">
              Delete all your activity but keep your account and sign-in.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setConfirmPurge(true)}
            className="shrink-0 rounded-[7px] border border-rule-strong px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors hover:border-terra hover:text-terra-2"
          >
            Erase data
          </button>
        </div>
        <div className="mt-3 flex flex-col gap-3 border-t border-rule pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-[13.5px] font-medium text-ink">Delete my account</p>
            <p className="text-[12.5px] text-ink-3">
              Permanently remove your account and all data. This cannot be undone.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="shrink-0 rounded-[7px] bg-destructive px-3.5 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
          >
            Delete account
          </button>
        </div>
      </section>

      <ConfirmDialog
        open={confirmPurge}
        onOpenChange={setConfirmPurge}
        title="Erase all your data?"
        description="Every record you've created will be permanently deleted. Your account and sign-in remain. Consider exporting first."
        confirmLabel="Erase everything"
        destructive
        pending={purgeMutation.isPending}
        onConfirm={() => purgeMutation.mutate()}
      />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete your account?"
        description="This permanently deletes your account and all data, and signs you out. This cannot be undone."
        confirmLabel="Delete account"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => deleteMutation.mutate()}
      />
    </div>
  );
}
