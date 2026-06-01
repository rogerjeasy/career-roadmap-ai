import { cn } from "@/lib/utils";
import type { SalaryBenchmark } from "@/types/market.types";

export interface SalaryBenchmarkCardProps {
  benchmark: SalaryBenchmark;
  className?: string;
}

function fmt(n: number, currency: string): string {
  const value = n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`;
  return `${currency}${value}`;
}

export function SalaryBenchmarkCard({ benchmark, className }: SalaryBenchmarkCardProps) {
  const { p25, p50, p75, currency } = benchmark;
  // Position of the median marker within the p25–p75 range.
  const range = Math.max(p75 - p25, 1);
  const medianPct = Math.max(4, Math.min(96, ((p50 - p25) / range) * 100));

  return (
    <div className={cn("rounded-[12px] border border-rule bg-paper p-6", className)}>
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h2 className="font-serif text-[16px] font-medium tracking-[-0.01em] text-ink">
          Salary benchmark
        </h2>
        <span className="text-[12px] text-ink-3">{benchmark.location}</span>
      </div>
      <p className="mb-5 text-[12.5px] text-ink-3">{benchmark.role}</p>

      <div className="mb-2 flex items-end justify-center gap-1">
        <span className="font-serif text-[34px] font-medium leading-none text-ink">
          {fmt(p50, currency)}
        </span>
        <span className="mb-1 text-[12px] text-ink-3">median</span>
      </div>

      {/* Range bar */}
      <div className="relative mt-6 h-2 rounded-full bg-bg-3">
        <div className="absolute inset-y-0 left-0 right-0 rounded-full bg-green-soft" />
        <div
          className="absolute top-1/2 left-[--mleft] h-4 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-green"
          style={{ "--mleft": `${medianPct}%` } as React.CSSProperties}
        />
      </div>
      <div className="mt-2 flex justify-between text-[11.5px] text-ink-3">
        <span>{fmt(p25, currency)} · 25th</span>
        <span>{fmt(p75, currency)} · 75th</span>
      </div>
    </div>
  );
}
