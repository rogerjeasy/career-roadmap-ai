"use client";

import { useState, type FormEvent, type ReactElement } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  applicationsApi,
  type Application,
  type ApplicationOutcome,
  type ApplicationStatus,
} from "@/lib/api/applications";
import {
  STAGES,
  STATUS_LABEL,
  STATUS_TONE,
  OUTCOMES,
  OUTCOME_LABEL,
} from "@/lib/applications-meta";
import { ROUTES, QUERY_KEYS } from "@/lib/constants";
import { formatDateTime, formatRelative } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-[8px] border border-rule bg-bg px-3.5 py-2.5 text-[13.5px] text-ink placeholder:text-ink-3 focus:border-green focus:bg-paper focus:outline-none";

const SECTION_CLASS = "mb-6 rounded-[12px] border border-rule bg-paper p-5";

const GHOST_BTN =
  "rounded-[7px] border border-rule px-3.5 py-2 text-[13px] font-medium text-ink transition-colors hover:border-rule-strong disabled:opacity-50";

const LABEL_CLASS =
  "mb-2 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3";

async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Copied");
  } catch {
    toast.error("Couldn't copy");
  }
}

export default function ApplicationDetailPage() {
  const params = useParams<{ appId: string }>();
  const appId = params.appId;
  const queryClient = useQueryClient();
  const router = useRouter();

  const [jobDescription, setJobDescription] = useState("");
  const [notes, setNotes] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: app, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.application(appId),
    queryFn: () => applicationsApi.get(appId),
    enabled: Boolean(appId),
    retry: false,
  });

  // Hydrate the editable fields once the application loads (render-phase pattern).
  const [hydratedFrom, setHydratedFrom] = useState<Application | null>(null);
  if (app && app !== hydratedFrom) {
    setHydratedFrom(app);
    setJobDescription(app.jobDescription);
    setNotes(app.notes);
  }

  const setData = (data: Application) =>
    queryClient.setQueryData(QUERY_KEYS.application(appId), data);

  const updateMutation = useMutation({
    mutationFn: (input: Parameters<typeof applicationsApi.update>[1]) =>
      applicationsApi.update(appId, input),
    onSuccess: (data) => {
      setData(data);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.applications });
      toast.success("Saved");
    },
    onError: () => toast.error("Couldn't save."),
  });

  const tailorMutation = useMutation({
    mutationFn: () => applicationsApi.tailorCv(appId),
    onSuccess: (data) => {
      setData(data);
      toast.success("CV tailored to this job");
    },
    onError: () => toast.error("Couldn't tailor the CV. Have you imported a CV?"),
  });

  const coverMutation = useMutation({
    mutationFn: () => applicationsApi.coverLetter(appId),
    onSuccess: (data) => {
      setData(data);
      toast.success("Cover letter generated");
    },
    onError: () => toast.error("Couldn't generate the cover letter."),
  });

  const deleteMutation = useMutation({
    mutationFn: () => applicationsApi.remove(appId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.applications });
      toast.success("Application removed");
      router.push(ROUTES.applications);
    },
  });

  const backLink = (
    <Link
      href={ROUTES.applications}
      className="mb-4 inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
    >
      ← Applications
    </Link>
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[820px] px-4 pb-24 pt-7 sm:px-7">
        {backLink}
        <LoadingSpinner fullPage label="Loading…" />
      </div>
    );
  }

  if (isError || !app) {
    return (
      <div className="mx-auto max-w-[820px] px-4 pb-24 pt-7 sm:px-7">
        {backLink}
        <EmptyState title="Application not found" description="It may have been removed." />
      </div>
    );
  }

  const tailored = app.tailoredCv;

  return (
    <div className="mx-auto max-w-[820px] px-4 pb-24 pt-7 sm:px-7">
      {backLink}
      <PageHeader
        eyebrow={app.company}
        title={app.role}
        description={[app.location, app.salary].filter(Boolean).join(" · ") || undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={app.status}
              onChange={(e) => updateMutation.mutate({ status: e.target.value as ApplicationStatus })}
              className="rounded-[7px] border border-rule bg-bg px-3 py-2 text-[13px] text-ink focus:border-green focus:outline-none"
            >
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
            {app.status === "closed" && (
              <select
                value={app.outcome ?? ""}
                onChange={(e) =>
                  updateMutation.mutate({
                    outcome: (e.target.value || null) as ApplicationOutcome | null,
                  })
                }
                className="rounded-[7px] border border-rule bg-bg px-3 py-2 text-[13px] text-ink focus:border-green focus:outline-none"
              >
                <option value="">Outcome…</option>
                {OUTCOMES.map((o) => (
                  <option key={o} value={o}>
                    {OUTCOME_LABEL[o]}
                  </option>
                ))}
              </select>
            )}
          </div>
        }
      />

      {app.jobUrl && (
        <a
          href={app.jobUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-6 inline-block text-[12.5px] font-medium text-terra transition-colors hover:text-terra-2"
        >
          View job posting →
        </a>
      )}

      <section className={SECTION_CLASS}>
        <p className={LABEL_CLASS}>Job description</p>
        <textarea
          value={jobDescription}
          onChange={(e) => setJobDescription(e.target.value)}
          placeholder="Paste the job description here — it powers the CV tailoring and cover letter."
          rows={6}
          className={`${FIELD_CLASS} resize-y`}
        />
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={() => updateMutation.mutate({ jobDescription })}
            disabled={updateMutation.isPending}
            className={GHOST_BTN}
          >
            Save description
          </button>
        </div>
      </section>

      <section className="mb-6 grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => tailorMutation.mutate()}
          disabled={tailorMutation.isPending}
          className="rounded-[10px] border border-rule bg-paper px-4 py-3 text-left transition-colors hover:border-green disabled:opacity-60"
        >
          <p className="text-[13.5px] font-medium text-ink">
            {tailorMutation.isPending ? "Tailoring CV…" : "Tailor my CV to this job"}
          </p>
          <p className="mt-0.5 text-[12px] text-ink-3">
            Rewrites your real CV bullets + finds keyword gaps
          </p>
        </button>
        <button
          type="button"
          onClick={() => coverMutation.mutate()}
          disabled={coverMutation.isPending}
          className="rounded-[10px] border border-rule bg-paper px-4 py-3 text-left transition-colors hover:border-green disabled:opacity-60"
        >
          <p className="text-[13.5px] font-medium text-ink">
            {coverMutation.isPending ? "Writing letter…" : "Draft a cover letter"}
          </p>
          <p className="mt-0.5 text-[12px] text-ink-3">Tailored to the role, from your CV</p>
        </button>
      </section>

      {tailored && (
        <section className="mb-6 space-y-4 rounded-[12px] border border-green bg-paper p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
              Tailored CV
            </h2>
            <span className="rounded-[6px] bg-green-soft px-2.5 py-1 text-[12px] font-semibold text-green-2">
              {tailored.fitScore}% fit
            </span>
          </div>
          {tailored.summary && (
            <p className="text-[13.5px] leading-relaxed text-ink-2">{tailored.summary}</p>
          )}

          {tailored.changes.length > 0 ? (
            <div>
              <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                What changed
              </p>
              <ul className="mt-2 space-y-2.5">
                {tailored.changes.map((c, i) => (
                  <li key={i} className="overflow-hidden rounded-[8px] border border-rule">
                    {c.before && (
                      <p className="border-b border-rule bg-terra-faint px-3 py-2 text-[12.5px] leading-relaxed text-terra-2">
                        <span className="mr-1.5 select-none font-semibold">−</span>
                        <span className="line-through decoration-terra/50">{c.before}</span>
                      </p>
                    )}
                    {c.after && (
                      <p className="bg-green-faint px-3 py-2 text-[12.5px] leading-relaxed text-green-2">
                        <span className="mr-1.5 select-none font-semibold">+</span>
                        {c.after}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            tailored.bullets.length > 0 && (
              <div>
                <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                  Rewritten bullets
                </p>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-ink-2">
                  {tailored.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            )
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            {tailored.matchedKeywords.length > 0 && (
              <div>
                <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-green-2">
                  You match
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {tailored.matchedKeywords.map((k) => (
                    <span key={k} className="rounded-[5px] bg-green-soft px-2 py-0.5 text-[11px] font-medium text-green-2">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {tailored.missingKeywords.length > 0 && (
              <div>
                <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-terra-2">
                  Gaps to address
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {tailored.missingKeywords.map((k) => (
                    <span key={k} className="rounded-[5px] bg-terra-soft px-2 py-0.5 text-[11px] font-medium text-terra-2">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
          {tailored.advice && (
            <p className="rounded-[8px] bg-bg-2 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-ink-2">
              {tailored.advice}
            </p>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => copy([tailored.summary, "", ...tailored.bullets.map((b) => `• ${b}`)].join("\n"))}
              className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-rule-strong"
            >
              Copy
            </button>
          </div>
        </section>
      )}

      {app.coverLetter && (
        <section className="mb-6 space-y-3 rounded-[12px] border border-green bg-paper p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-serif text-[17px] font-medium tracking-[-0.01em] text-ink">
              Cover letter
            </h2>
            <button
              type="button"
              onClick={() => app.coverLetter && copy(app.coverLetter.content)}
              className="rounded-[7px] border border-rule px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-rule-strong"
            >
              Copy
            </button>
          </div>
          <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">
            {app.coverLetter.content}
          </p>
        </section>
      )}

      <RemindersPanel app={app} setData={setData} />

      <StageNotesEditor app={app} setData={setData} />

      <Timeline app={app} />

      <section className={SECTION_CLASS}>
        <p className={LABEL_CLASS}>General notes</p>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Anything that isn't tied to a single stage…"
          rows={3}
          className={`${FIELD_CLASS} resize-y`}
        />
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            onClick={() => updateMutation.mutate({ notes })}
            disabled={updateMutation.isPending}
            className={GHOST_BTN}
          >
            Save notes
          </button>
        </div>
      </section>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          className="text-[12.5px] font-medium text-ink-3 transition-colors hover:text-destructive"
        >
          Delete application
        </button>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this application?"
        description={`"${app.role} at ${app.company}" and its tailored CV and cover letter will be removed.`}
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => deleteMutation.mutate()}
      />
    </div>
  );
}

interface PanelProps {
  app: Application;
  setData: (data: Application) => void;
}

function RemindersPanel({ app, setData }: PanelProps): ReactElement {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");

  const refresh = (data: Application) => {
    setData(data);
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.applications });
  };

  const addMutation = useMutation({
    mutationFn: (input: { title: string; dueAt: string }) =>
      applicationsApi.addReminder(app.id, input),
    onSuccess: (data) => {
      refresh(data);
      setTitle("");
      setDueAt("");
      toast.success("Reminder added");
    },
    onError: () => toast.error("Couldn't add the reminder."),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      applicationsApi.setReminderDone(app.id, id, done),
    onSuccess: refresh,
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => applicationsApi.removeReminder(app.id, id),
    onSuccess: refresh,
  });

  const onAdd = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !dueAt) return;
    addMutation.mutate({ title: title.trim(), dueAt: new Date(dueAt).toISOString() });
  };

  const now = new Date().getTime();

  return (
    <section className={SECTION_CLASS}>
      <p className={LABEL_CLASS}>Reminders</p>

      {app.reminders.length > 0 && (
        <ul className="mb-4 space-y-2">
          {app.reminders.map((r) => {
            const overdue = !r.done && new Date(r.dueAt).getTime() <= now;
            return (
              <li
                key={r.id}
                className="flex items-center gap-3 rounded-[8px] border border-rule bg-bg/40 px-3 py-2"
              >
                <input
                  type="checkbox"
                  checked={r.done}
                  onChange={(e) => toggleMutation.mutate({ id: r.id, done: e.target.checked })}
                  className="size-4 shrink-0 accent-[var(--color-green)]"
                  aria-label={`Mark "${r.title}" done`}
                />
                <div className="min-w-0 flex-1">
                  <p className={cn("truncate text-[13px]", r.done ? "text-ink-3 line-through" : "text-ink")}>
                    {r.title}
                  </p>
                  <p className={cn("text-[11.5px]", overdue ? "font-medium text-terra-2" : "text-ink-3")}>
                    {overdue ? "Overdue · " : ""}
                    {formatDateTime(r.dueAt)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeMutation.mutate(r.id)}
                  className="shrink-0 text-[11.5px] font-medium text-ink-3 transition-colors hover:text-destructive"
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <form onSubmit={onAdd} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Follow up, prep for interview…"
          className={cn(FIELD_CLASS, "sm:flex-1")}
        />
        <input
          type="datetime-local"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          className={cn(FIELD_CLASS, "sm:w-[210px]")}
        />
        <button
          type="submit"
          disabled={!title.trim() || !dueAt || addMutation.isPending}
          className="rounded-[7px] bg-ink px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-green-2 disabled:opacity-50"
        >
          Add
        </button>
      </form>
    </section>
  );
}

function StageNotesEditor({ app, setData }: PanelProps): ReactElement {
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<ApplicationStatus>(app.status);
  const [draft, setDraft] = useState(app.stageNotes[app.status] ?? "");
  // Reset the draft whenever the selected stage (or its saved value) changes —
  // the React-blessed "adjust state during render" pattern (no effect needed).
  const sig = `${stage}:${app.stageNotes[stage] ?? ""}`;
  const [lastSig, setLastSig] = useState(sig);
  if (lastSig !== sig) {
    setLastSig(sig);
    setDraft(app.stageNotes[stage] ?? "");
  }

  const saveMutation = useMutation({
    mutationFn: (note: string) => applicationsApi.setStageNote(app.id, stage, note),
    onSuccess: (data) => {
      setData(data);
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.applications });
      toast.success(`Saved ${STATUS_LABEL[stage]} note`);
    },
    onError: () => toast.error("Couldn't save the note."),
  });

  const stagesWithNotes = STAGES.filter((s) => (app.stageNotes[s] ?? "").trim());

  return (
    <section className={SECTION_CLASS}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          Stage notes
        </p>
        <select
          value={stage}
          onChange={(e) => setStage(e.target.value as ApplicationStatus)}
          className="rounded-[7px] border border-rule bg-bg px-3 py-1.5 text-[12.5px] text-ink focus:border-green focus:outline-none"
        >
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
              {(app.stageNotes[s] ?? "").trim() ? " •" : ""}
            </option>
          ))}
        </select>
      </div>

      {stagesWithNotes.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {stagesWithNotes.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStage(s)}
              className={cn(
                "rounded-[5px] px-2 py-0.5 text-[11px] font-medium transition-colors",
                s === stage ? STATUS_TONE[s] : "bg-bg-2 text-ink-2 hover:text-ink",
              )}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
      )}

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={`Notes for the ${STATUS_LABEL[stage]} stage — interviewers, prep, questions asked…`}
        rows={3}
        className={`${FIELD_CLASS} resize-y`}
      />
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => saveMutation.mutate(draft)}
          disabled={saveMutation.isPending || draft === (app.stageNotes[stage] ?? "")}
          className={GHOST_BTN}
        >
          Save {STATUS_LABEL[stage]} note
        </button>
      </div>
    </section>
  );
}

function Timeline({ app }: { app: Application }): ReactElement | null {
  if (app.timeline.length === 0) return null;
  return (
    <section className={SECTION_CLASS}>
      <p className={LABEL_CLASS}>Timeline</p>
      <ol className="space-y-3">
        {app.timeline.map((e, i) => (
          <li key={i} className="flex gap-3">
            <div className="flex flex-col items-center pt-0.5">
              <span className="size-2.5 shrink-0 rounded-full bg-green" />
              {i < app.timeline.length - 1 && <span className="mt-1 w-px flex-1 bg-rule" />}
            </div>
            <div className="min-w-0 pb-1">
              <p className="text-[13px] font-medium text-ink">
                {STATUS_LABEL[e.status]}
                {e.outcome ? ` · ${OUTCOME_LABEL[e.outcome]}` : ""}
              </p>
              {e.at && (
                <p className="text-[11.5px] text-ink-3">
                  {formatDateTime(e.at)} · {formatRelative(e.at)}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
