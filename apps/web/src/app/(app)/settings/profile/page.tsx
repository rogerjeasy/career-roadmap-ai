"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/hooks/use-auth";
import { getSession, updateUserProfileContext } from "@/lib/api/session";
import { userApi } from "@/lib/api/user";
import { useAuthStore } from "@/store/auth.store";
import { fixMojibake } from "@/lib/utils";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { PageHeader } from "@/components/shared/page-header";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none disabled:opacity-60";

export default function ProfileSettingsPage() {
  const { user } = useAuth();
  const setUser = useAuthStore((s) => s.setUser);
  const queryClient = useQueryClient();
  const { data: session } = useQuery({
    queryKey: QUERY_KEYS.session,
    queryFn: getSession,
    staleTime: 60 * 1000,
  });

  const ctx = session?.userProfileContext;
  const [displayName, setDisplayName] = useState(user?.displayName ?? "");
  const [targetRole, setTargetRole] = useState(ctx?.targetRole ? fixMojibake(ctx.targetRole) : "");
  const [currentRole, setCurrentRole] = useState(ctx?.currentRole ? fixMojibake(ctx.currentRole) : "");

  const saveMutation = useMutation({
    mutationFn: async () => {
      const trimmedName = displayName.trim();
      // Display name lives on the user record + Firebase Auth; target/current
      // role live in the session's profile context — persist both in parallel.
      const [profile] = await Promise.all([
        trimmedName && trimmedName !== (user?.displayName ?? "")
          ? userApi.updateMe({ displayName: trimmedName })
          : Promise.resolve(null),
        updateUserProfileContext({
          targetRole: targetRole.trim() || null,
          currentRole: currentRole.trim() || null,
        }),
      ]);
      return profile;
    },
    onSuccess: (profile) => {
      if (profile) setUser(profile);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.session });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.me });
      toast.success("Profile saved");
    },
    onError: () => toast.error("Couldn't save your profile. Please try again."),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    saveMutation.mutate();
  };

  return (
    <div className="mx-auto max-w-[640px] px-7 pb-24 pt-7">
      <Link
        href={ROUTES.settings}
        className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
      >
        ← Settings
      </Link>
      <PageHeader eyebrow="Account" title="Profile" description="How you and your goal appear across the app." />

      <form onSubmit={onSubmit} className="space-y-4 rounded-[12px] border border-rule bg-paper p-6">
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Display name</span>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Ada Lovelace" className={FIELD_CLASS} />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Email</span>
          <input value={user?.email ?? ""} disabled className={FIELD_CLASS} />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Current role</span>
            <input value={currentRole} onChange={(e) => setCurrentRole(e.target.value)} placeholder="Full-Stack Engineer" className={FIELD_CLASS} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">Target role</span>
            <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} placeholder="AI Systems Engineer" className={FIELD_CLASS} />
          </label>
        </div>
        <div className="flex justify-end pt-1">
          <button
            type="submit"
            disabled={saveMutation.isPending}
            className="rounded-[7px] bg-ink px-5 py-2.5 text-[13.5px] font-medium text-bg transition-colors duration-150 hover:bg-green-2 disabled:opacity-50"
          >
            {saveMutation.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
