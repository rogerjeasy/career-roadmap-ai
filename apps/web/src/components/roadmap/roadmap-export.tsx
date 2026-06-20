"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { exportsApi } from "@/lib/api/exports";

export interface RoadmapExportProps {
  roadmapId: string;
}

export function RoadmapExport({ roadmapId }: RoadmapExportProps): React.ReactElement {
  const md = useMutation({
    mutationFn: () => exportsApi.roadmapMarkdown(roadmapId),
    onSuccess: () => toast.success("Markdown downloaded"),
    onError: () => toast.error("Couldn't export Markdown."),
  });

  const ics = useMutation({
    mutationFn: () => exportsApi.roadmapIcs(roadmapId),
    onSuccess: () => toast.success("Calendar (.ics) downloaded"),
    onError: () => toast.error("Couldn't export calendar."),
  });

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => md.mutate()}
        disabled={md.isPending}
        className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink-2 transition-colors hover:border-rule-strong disabled:opacity-50"
      >
        Export Markdown
      </button>
      <button
        type="button"
        onClick={() => ics.mutate()}
        disabled={ics.isPending}
        className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink-2 transition-colors hover:border-rule-strong disabled:opacity-50"
      >
        Add to calendar
      </button>
    </div>
  );
}
