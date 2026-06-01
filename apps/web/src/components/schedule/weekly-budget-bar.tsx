import { cn } from "@/lib/utils";

export interface BudgetCategory {
  id: string;
  label: string;
  hoursLogged: number;
  hoursTarget: number;
  tone: "green" | "terra" | "gold" | "ink";
}

export interface WeeklyBudgetBarProps {
  categories: BudgetCategory[];
  className?: string;
}

const TONE_FILL: Record<BudgetCategory["tone"], string> = {
  green: "bg-green",
  terra: "bg-terra",
  gold: "bg-gold",
  ink: "bg-ink",
};

export function WeeklyBudgetBar({ categories, className }: WeeklyBudgetBarProps) {
  const logged = categories.reduce((s, c) => s + c.hoursLogged, 0);
  const target = categories.reduce((s, c) => s + c.hoursTarget, 0);

  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">Weekly budget</h3>
        <span className="font-mono text-[13px] text-ink-2">
          {logged.toFixed(1).replace(/\.0$/, "")} / {target} h
        </span>
      </div>
      <ul className="space-y-3.5">
        {categories.map((c) => {
          const pct = c.hoursTarget > 0 ? Math.min((c.hoursLogged / c.hoursTarget) * 100, 100) : 0;
          return (
            <li key={c.id}>
              <div className="mb-1 flex items-center justify-between text-[12.5px]">
                <span className="text-ink-2">{c.label}</span>
                <span className="font-mono text-[11.5px] text-ink-3">
                  {c.hoursLogged.toFixed(1).replace(/\.0$/, "")}/{c.hoursTarget}h
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-bg-3">
                <div
                  className={cn("h-full w-[--bar] rounded-full transition-[width] duration-500", TONE_FILL[c.tone])}
                  style={{ "--bar": `${pct}%` } as React.CSSProperties}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
