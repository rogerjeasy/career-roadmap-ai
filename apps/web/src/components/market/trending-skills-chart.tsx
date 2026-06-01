import { cn } from "@/lib/utils";
import type { TrendingSkill } from "@/types/market.types";

export interface TrendingSkillsChartProps {
  skills: TrendingSkill[];
  className?: string;
}

export function TrendingSkillsChart({ skills, className }: TrendingSkillsChartProps) {
  const max = Math.max(...skills.map((s) => s.demandIndex), 1);

  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <h2 className="mb-1 font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
        Trending skills
      </h2>
      <p className="mb-5 text-[12.5px] text-ink-3">Relative demand in your target market</p>

      <ul className="space-y-3.5">
        {skills.map((skill) => {
          const width = (skill.demandIndex / max) * 100;
          const up = skill.deltaPct >= 0;
          return (
            <li key={skill.name}>
              <div className="mb-1 flex items-center justify-between text-[12.5px]">
                <span className="font-medium text-ink">{skill.name}</span>
                <span className={cn("font-mono text-[11.5px]", up ? "text-green-2" : "text-terra-2")}>
                  {up ? "▲" : "▼"} {Math.abs(skill.deltaPct)}%
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-bg-3">
                <div
                  className="h-full w-[--bar] rounded-full bg-green transition-[width] duration-500 ease-out"
                  style={{ "--bar": `${width}%` } as React.CSSProperties}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
