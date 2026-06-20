"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { snapshotsApi, type RoadmapSnapshot } from "@/lib/api/snapshots";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { formatRelative } from "@/lib/date";

export interface RoadmapVersionsProps {
  roadmapId: string;
}

export function RoadmapVersions({ roadmapId }: RoadmapVersionsProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [pendingRestore, setPendingRestore] = useState<RoadmapSnapshot | null>(null);

  const { data: snapshots, isLoading } = useQuery({
    queryKey: QUERY_KEYS.roadmapSnapshots(roadmapId),
    queryFn: () => snapshotsApi.list(roadmapId),
    staleTime: 20 * 1000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.roadmapSnapshots(roadmapId) });
  };

  const createMutation = useMutation({
    mutationFn: () => snapshotsApi.create(roadmapId, label.trim()),
    onSuccess: () => {
      invalidate();
      toast.success("Snapshot saved");
      setLabel("");
    },
    onError: () => toast.error("Couldn't save a snapshot."),
  });

  const restoreMutation = useMutation({
    mutationFn: (id: string) => snapshotsApi.restore(id),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.roadmap(roadmapId) });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.roadmapProgress(roadmapId) });
      toast.success("Roadmap restored — the previous state was auto-saved");
      setPendingRestore(null);
    },
    onError: () => toast.error("Couldn't restore that version."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => snapshotsApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Snapshot deleted");
    },
  });

  return (
    <div className="rounded-[12px] border border-rule bg-paper p-5">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
            Version history
          </h2>
          <p className="text-[12.5px] text-ink-3">
            Save a snapshot before big changes — restoring auto-saves your current state.
          </p>
        </div>
        <div className="flex gap-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (optional)"
            className="w-full rounded-[8px] border border-rule bg-bg px-3 py-2 text-[12.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none sm:w-44"
          />
          <button
            type="button"
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
            className="shrink-0 rounded-[7px] bg-ink px-3.5 py-2 text-[12.5px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
          >
            Save snapshot
          </button>
        </div>
      </div>

      {isLoading ? (
        <LoadingSpinner label="Loading versions…" />
      ) : !snapshots || snapshots.length === 0 ? (
        <p className="rounded-[9px] border border-dashed border-rule-strong bg-bg px-4 py-6 text-center text-[12.5px] text-ink-3">
          No saved versions yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {snapshots.map((s: RoadmapSnapshot) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-3 rounded-[9px] border border-rule bg-bg px-3.5 py-2.5"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[13px] font-medium text-ink">{s.label}</span>
                  {s.auto && (
                    <span className="shrink-0 rounded-[4px] bg-bg-2 px-1.5 py-0.5 text-[10px] font-medium text-ink-3">
                      auto
                    </span>
                  )}
                </div>
                <p className="text-[11.5px] text-ink-3">
                  {s.phaseCount} phases
                  {s.createdAt ? ` · ${formatRelative(s.createdAt)}` : ""}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => setPendingRestore(s)}
                  className="text-[12px] font-medium text-terra transition-colors hover:text-terra-2"
                >
                  Restore
                </button>
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(s.id)}
                  className="text-[12px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={pendingRestore !== null}
        onOpenChange={(open) => !open && setPendingRestore(null)}
        title="Restore this version?"
        description="Your current roadmap will be replaced with this snapshot. The current state is auto-saved first, so you can undo."
        confirmLabel="Restore"
        pending={restoreMutation.isPending}
        onConfirm={() => pendingRestore && restoreMutation.mutate(pendingRestore.id)}
      />
    </div>
  );
}
