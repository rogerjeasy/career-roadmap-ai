"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { evidenceApi, type EvidenceCreateInput } from "@/lib/api/evidence";
import { QUERY_KEYS } from "@/lib/constants";

/**
 * Cross-feature link: promote any artefact (a shipped portfolio project, a
 * merged open-source contribution, …) into the Evidence Vault so it can back
 * CVs, credentials, and storytelling. Reuses the evidence domain — no new
 * backend surface needed.
 */
export function useAddToEvidence() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: EvidenceCreateInput) => evidenceApi.create(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.evidence });
      toast.success("Added to your Evidence Vault");
    },
    onError: () => toast.error("Couldn't add that to your evidence."),
  });
}
