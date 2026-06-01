import { cn } from "@/lib/utils";

export interface ScheduleBlock {
  day: number; // 0 = Mon … 6 = Sun
  label: string;
  category: "build" | "read" | "network" | "review";
}

export interface WeeklyGridProps {
  blocks: ScheduleBlock[];
  className?: string;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const CATEGORY_STYLE: Record<ScheduleBlock["category"], string> = {
  build: "bg-green-soft text-green-2",
  read: "bg-bg-3 text-ink-2",
  network: "bg-terra-soft text-terra-2",
  review: "bg-gold-soft text-gold",
};

export function WeeklyGrid({ blocks, className }: WeeklyGridProps) {
  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-4 sm:p-6", className)}>
      <h3 className="mb-4 font-serif text-[15px] font-medium tracking-[-0.01em] text-ink">This week</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {DAYS.map((day, i) => {
          const dayBlocks = blocks.filter((b) => b.day === i);
          return (
            <div key={day} className="min-w-0">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">{day}</p>
              <div className="space-y-1.5">
                {dayBlocks.length === 0 ? (
                  <div className="rounded-[6px] border border-dashed border-rule px-2 py-2 text-center text-[11px] text-ink-3">
                    —
                  </div>
                ) : (
                  dayBlocks.map((b, bi) => (
                    <div
                      key={bi}
                      className={cn("rounded-[6px] px-2 py-1.5 text-[11.5px] font-medium leading-snug", CATEGORY_STYLE[b.category])}
                    >
                      {b.label}
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
