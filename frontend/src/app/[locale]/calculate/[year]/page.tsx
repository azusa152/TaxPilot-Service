"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { Link, useRouter } from "@/i18n/navigation";
import { useUser } from "@/lib/user-context";
import {
  calculateTax,
  ApiError,
  type TaxCalculationResult,
} from "@/lib/api-client";
import { formatJPY } from "@/lib/format";
import { RequireUser } from "@/components/shared/RequireUser";
import { TaxBreakdownChart } from "@/components/shared/TaxBreakdownChart";

function CalculateContent() {
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i);

  const t = useTranslations("calculate");
  const tResult = useTranslations("calculate.result");
  const tError = useTranslations("calculate.error");
  const { user } = useUser();
  const router = useRouter();
  const params = useParams();
  const year = Number(params.year);

  const [calculating, setCalculating] = useState(false);
  const [result, setResult] = useState<TaxCalculationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleCalculate() {
    if (!user) return;
    setCalculating(true);
    setError(null);

    try {
      const data = await calculateTax(user.id, year);
      setResult(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError(tError("noData"));
      } else {
        setError(tError("calculationFailed"));
      }
    } finally {
      setCalculating(false);
    }
  }

  function handleRecalculate() {
    setResult(null);
    setError(null);
    handleCalculate();
  }

  function handleYearChange(newYear: number) {
    setResult(null);
    setError(null);
    router.push(`/calculate/${newYear}`);
  }

  const deductionRows: { labelKey: string; value: number }[] = result
    ? [
        { labelKey: "basicDeduction", value: result.basic_deduction },
        {
          labelKey: "socialInsuranceDeduction",
          value: result.social_insurance_deduction,
        },
        {
          labelKey: "lifeInsuranceDeduction",
          value: result.life_insurance_deduction,
        },
        { labelKey: "spouseDeduction", value: result.spouse_deduction },
        {
          labelKey: "dependentsDeduction",
          value: result.dependents_deduction,
        },
        { labelKey: "idecoDeduction", value: result.ideco_deduction },
      ]
    : [];

  return (
    <div className="mx-auto max-w-2xl print:max-w-none">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <div className="flex items-center gap-2 print:hidden">
          <label htmlFor="year-select" className="text-sm font-medium">
            {t("yearLabel")}
          </label>
          <select
            id="year-select"
            value={year}
            onChange={(e) => handleYearChange(Number(e.target.value))}
            className="rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {yearOptions.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Calculate button / pre-calculation state */}
      {!result && (
        <div className="space-y-4">
          <button
            type="button"
            onClick={handleCalculate}
            disabled={calculating}
            className="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {calculating ? t("calculating") : t("calculate")}
          </button>

          {calculating && (
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <p className="text-sm text-muted-foreground">
                {t("calculating")}
              </p>
            </div>
          )}

          {error && (
            <div className="space-y-3">
              <p className="text-sm text-destructive">{error}</p>
              <div className="flex flex-wrap gap-3">
                <Link
                  href="/income/new"
                  className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
                >
                  {t("addIncome")}
                </Link>
                <Link
                  href={`/profile/${year}`}
                  className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
                >
                  {t("editProfile")}
                </Link>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Results panel */}
      {result && (
        <div className="space-y-6 print:space-y-4">
          {/* Furusato Nozei limit — highlighted prominently */}
          <div className="rounded-lg border-2 border-primary bg-primary/5 p-4">
            <p className="text-sm font-medium text-muted-foreground">
              {tResult("furusatoLimit")}
            </p>
            <p className="mt-1 text-3xl font-bold text-primary">
              {formatJPY(result.furusato_limit)}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              {tResult("furusatoNote")}
            </p>
          </div>

          {/* Income summary */}
          <div className="rounded-lg border p-4">
            <h2 className="mb-3 text-lg font-semibold">
              {tResult("title")}
            </h2>
            <dl className="space-y-2 text-sm">
              <ResultRow
                label={tResult("grossSalary")}
                value={formatJPY(result.gross_salary)}
              />
              <ResultRow
                label={tResult("salaryIncomeDeduction")}
                value={`-${formatJPY(result.salary_income_deduction)}`}
                muted
              />
              <ResultRow
                label={tResult("totalIncome")}
                value={formatJPY(result.total_income)}
                bold
              />
            </dl>
          </div>

          {/* Deductions breakdown */}
          <div className="rounded-lg border p-4">
            <h2 className="mb-3 text-lg font-semibold">
              {tResult("deductions")}
            </h2>
            <dl className="space-y-2 text-sm">
              {deductionRows.map((row) => (
                <ResultRow
                  key={row.labelKey}
                  label={tResult(row.labelKey)}
                  value={
                    row.value > 0 ? `-${formatJPY(row.value)}` : formatJPY(0)
                  }
                  muted={row.value === 0}
                />
              ))}
              <div className="border-t pt-2">
                <ResultRow
                  label={tResult("totalDeductions")}
                  value={`-${formatJPY(result.total_deductions)}`}
                  bold
                />
              </div>
            </dl>
          </div>

          {/* Tax result */}
          <div className="rounded-lg border p-4">
            <dl className="space-y-2 text-sm">
              <ResultRow
                label={tResult("taxableIncome")}
                value={formatJPY(result.taxable_income)}
                bold
              />
              <ResultRow
                label={tResult("incomeTax")}
                value={formatJPY(result.income_tax)}
                bold
              />
            </dl>
          </div>

          {/* Visual breakdown chart */}
          <div className="rounded-lg border p-4 print:break-inside-avoid">
            <TaxBreakdownChart result={result} />
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-3 print:hidden">
            <button
              type="button"
              onClick={handleRecalculate}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              {t("recalculate")}
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
            >
              {t("print")}
            </button>
            <Link
              href={`/profile/${year}`}
              className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
            >
              {t("editProfile")}
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function ResultRow({
  label,
  value,
  bold,
  muted,
}: {
  label: string;
  value: string;
  bold?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <dt
        className={
          bold ? "font-semibold" : muted ? "text-muted-foreground" : ""
        }
      >
        {label}
      </dt>
      <dd className={bold ? "font-bold" : muted ? "text-muted-foreground" : "font-medium"}>
        {value}
      </dd>
    </div>
  );
}

export default function CalculateYearPage() {
  return (
    <RequireUser>
      <CalculateContent />
    </RequireUser>
  );
}
