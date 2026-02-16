"use client";

import { useTranslations } from "next-intl";
import { formatJPY } from "@/lib/format";
import type { TaxCalculationResult } from "@/lib/api-client";

interface TaxBreakdownChartProps {
  result: TaxCalculationResult;
}

interface BarSegment {
  label: string;
  value: number;
  colorClass: string;
}

export function TaxBreakdownChart({ result }: TaxBreakdownChartProps) {
  const t = useTranslations("calculate.chart");

  // gross_salary = salary_income_deduction + total_deductions + taxable_income
  const segments: BarSegment[] = [
    {
      label: t("salaryIncomeDeduction"),
      value: result.salary_income_deduction,
      colorClass: "bg-emerald-500",
    },
    {
      label: t("deductions"),
      value: result.total_deductions,
      colorClass: "bg-blue-500",
    },
    {
      label: t("taxableIncome"),
      value: result.taxable_income,
      colorClass: "bg-amber-500",
    },
  ];

  const total = result.gross_salary;
  if (total <= 0) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">{t("title")}</h3>

      {/* Stacked horizontal bar */}
      <div className="flex h-8 w-full overflow-hidden rounded-md">
        {segments.map((seg) => {
          const pct = (seg.value / total) * 100;
          if (pct <= 0) return null;
          return (
            <div
              key={seg.label}
              className={`${seg.colorClass} transition-all`}
              style={{ width: `${pct}%` }}
              title={`${seg.label}: ${formatJPY(seg.value)}`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1.5">
            <span
              className={`inline-block h-3 w-3 rounded-sm ${seg.colorClass}`}
            />
            <span className="text-muted-foreground">
              {seg.label}: {formatJPY(seg.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
