import { cn } from "@/lib/utils";
import type { CvSkill } from "@/types/onboarding.types";

export interface SkillComparisonTableProps {
  skills: CvSkill[];
  className?: string;
}

export function SkillComparisonTable({ skills, className }: SkillComparisonTableProps) {
  if (skills.length === 0) {
    return (
      <p className="rounded-[10px] border border-dashed border-rule-strong bg-paper px-4 py-6 text-center text-[13px] text-ink-3">
        No skills were detected in this document.
      </p>
    );
  }

  const strong = skills.filter((s) => s.level === "strong");
  const supporting = skills.filter((s) => s.level === "supporting");

  return (
    <div className={cn("space-y-5", className)}>
      <SkillGroup
        title="Strong skills"
        hint="Demonstrated repeatedly across roles and projects"
        skills={strong}
        tone="strong"
      />
      <SkillGroup
        title="Supporting skills"
        hint="Present but less central to your experience"
        skills={supporting}
        tone="supporting"
      />
    </div>
  );
}

interface SkillGroupProps {
  title: string;
  hint: string;
  skills: CvSkill[];
  tone: "strong" | "supporting";
}

function SkillGroup({ title, hint, skills, tone }: SkillGroupProps) {
  if (skills.length === 0) return null;
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
        <span className="text-[11.5px] text-ink-3">{skills.length}</span>
      </div>
      <p className="mb-2.5 text-[12px] text-ink-3">{hint}</p>
      <div className="flex flex-wrap gap-2">
        {skills.map((skill) => (
          <span
            key={skill.name}
            className={cn(
              "rounded-[6px] px-2.5 py-1 text-[12.5px] font-medium",
              tone === "strong"
                ? "bg-green-soft text-green-2"
                : "bg-bg-2 text-ink-2",
            )}
          >
            {skill.name}
          </span>
        ))}
      </div>
    </div>
  );
}
