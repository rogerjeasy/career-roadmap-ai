"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { mentorshipApi } from "@/lib/api/mentorship";
import { QUERY_KEYS } from "@/lib/constants";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

export interface MentorProfileFormProps {
  className?: string;
}

export function MentorProfileForm(_props: MentorProfileFormProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [headline, setHeadline] = useState("");
  const [bio, setBio] = useState("");
  const [expertise, setExpertise] = useState("");
  const [capacity, setCapacity] = useState("3");
  const [isActive, setIsActive] = useState(true);
  const [hydrated, setHydrated] = useState(false);

  const { data: profile, isLoading } = useQuery({
    queryKey: QUERY_KEYS.mentorProfile,
    queryFn: mentorshipApi.getProfile,
    staleTime: 30 * 1000,
  });

  useEffect(() => {
    if (profile && !hydrated) {
      setHeadline(profile.headline);
      setBio(profile.bio);
      setExpertise(profile.expertise.join(", "));
      setCapacity(String(profile.capacity));
      setIsActive(profile.isActive);
      setHydrated(true);
    }
  }, [profile, hydrated]);

  const saveMutation = useMutation({
    mutationFn: mentorshipApi.upsertProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mentorProfile });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mentors });
      toast.success("Mentor profile saved");
    },
    onError: () => toast.error("Couldn't save your profile."),
  });

  const deactivateMutation = useMutation({
    mutationFn: mentorshipApi.deactivateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mentorProfile });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.mentors });
      setIsActive(false);
      toast.success("You've opted out of mentoring");
    },
    onError: () => toast.error("Couldn't update your status."),
  });

  if (isLoading) return <LoadingSpinner fullPage label="Loading…" />;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!headline.trim()) return;
    saveMutation.mutate({
      headline: headline.trim(),
      bio: bio.trim(),
      capacity: Number(capacity) || 3,
      isActive,
      expertise: expertise
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-[12px] border border-rule bg-paper p-5">
      <p className="text-[13px] leading-relaxed text-ink-2">
        Opt in to mentor others. You'll appear in discovery for members whose goals
        match your expertise, and you decide which session requests to accept.
      </p>
      <input
        value={headline}
        onChange={(e) => setHeadline(e.target.value)}
        placeholder="Headline (e.g. Senior PM, ex-FAANG)"
        className={FIELD_CLASS}
      />
      <textarea
        value={bio}
        onChange={(e) => setBio(e.target.value)}
        placeholder="A short bio — what you can help with"
        rows={3}
        className={`${FIELD_CLASS} resize-y`}
      />
      <input
        value={expertise}
        onChange={(e) => setExpertise(e.target.value)}
        placeholder="Expertise areas — comma separated"
        className={FIELD_CLASS}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          value={capacity}
          onChange={(e) => setCapacity(e.target.value)}
          type="number"
          min="1"
          max="20"
          placeholder="Mentees you can take"
          className={FIELD_CLASS}
        />
        <label className="flex items-center gap-2 rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13px] text-ink-2">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 accent-green"
          />
          Listed &amp; accepting requests
        </label>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {profile && (
          <button
            type="button"
            onClick={() => deactivateMutation.mutate()}
            disabled={deactivateMutation.isPending}
            className="rounded-[7px] border border-rule px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors hover:border-rule-strong disabled:opacity-50"
          >
            Opt out
          </button>
        )}
        <button
          type="submit"
          disabled={!headline.trim() || saveMutation.isPending}
          className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving…" : profile ? "Update profile" : "Become a mentor"}
        </button>
      </div>
    </form>
  );
}
