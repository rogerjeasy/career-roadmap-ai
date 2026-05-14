import type { ReactNode } from "react";
import type { CvAnalysisResult } from "@/types/onboarding.types";

export interface CvContextCardProps {
  cvResult: CvAnalysisResult;
  userName?: string | null;
}

export function CvContextCard({ cvResult, userName }: CvContextCardProps) {
  const strongSkills = cvResult.skills
    .filter((s) => s.level === "strong")
    .slice(0, 5);
  const emergingSkills = cvResult.skills
    .filter((s) => s.level === "supporting")
    .slice(0, 3);
  const edu = cvResult.education[0];

  return (
    <aside className="rounded-2xl border border-rule bg-paper p-5">
      <div className="mb-3.5 flex items-center justify-between border-b border-rule pb-3">
        <h5 className="font-serif text-[14px] font-medium uppercase tracking-[0.04em] text-ink-3">
          From your CV
        </h5>
        <button
          type="button"
          className="font-serif text-[11px] italic font-medium text-terra hover:text-terra-2"
        >
          Edit
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {/* Current role */}
        {(cvResult.currentRole ?? userName) && (
          <CtxSection label="Current role">
            <p className="text-[13px] font-medium leading-snug text-ink">
              <em className="font-serif text-[14px] not-italic text-green">
                {cvResult.currentRole ?? "Professional"}
              </em>
              {cvResult.yearsOfExperience > 0 && (
                <>
                  <br />
                  <span className="text-[12.5px] font-normal text-ink-2">
                    {cvResult.yearsOfExperience} years · {cvResult.summary ? "See summary" : "experience"}
                  </span>
                </>
              )}
            </p>
          </CtxSection>
        )}

        {/* Strong skills */}
        {strongSkills.length > 0 && (
          <CtxSection label="Strongest skills">
            <div className="flex flex-wrap gap-1.5">
              {strongSkills.map((s) => (
                <SkillTag key={s.name}>{s.name}</SkillTag>
              ))}
            </div>
          </CtxSection>
        )}

        {/* Emerging signals */}
        {emergingSkills.length > 0 && (
          <CtxSection label="Emerging signals">
            <div className="flex flex-wrap gap-1.5">
              {emergingSkills.map((s) => (
                <SkillTag key={s.name}>{s.name}</SkillTag>
              ))}
            </div>
          </CtxSection>
        )}

        {/* Education */}
        {edu && (
          <CtxSection label="Education">
            <p className="text-[12.5px] leading-snug text-ink">
              {[edu.degree, edu.field].filter(Boolean).join(" — ")}
              {edu.institution && (
                <>
                  <br />
                  {edu.institution}
                  {edu.year ? `, ${edu.year}` : ""}
                </>
              )}
            </p>
          </CtxSection>
        )}

        {/* Standout impact */}
        {cvResult.projects[0]?.impact && (
          <CtxSection label="Standout impact">
            <p className="text-[12.5px] leading-relaxed text-ink">
              {cvResult.projects[0].impact}
            </p>
          </CtxSection>
        )}
      </div>
    </aside>
  );
}

function CtxSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-ink-3">
        {label}
      </p>
      {children}
    </div>
  );
}

function SkillTag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[4px] border border-rule bg-bg px-2 py-0.5 text-[11px] font-medium text-ink-2">
      {children}
    </span>
  );
}

