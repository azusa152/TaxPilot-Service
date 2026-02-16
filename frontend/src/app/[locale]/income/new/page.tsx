"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { useUser } from "@/lib/user-context";
import { createIncomeEntry, type IncomeType } from "@/lib/api-client";
import { inputClass } from "@/lib/utils";
import { RequireUser } from "@/components/shared/RequireUser";
import { FormField } from "@/components/shared/FormField";

const INCOME_TYPES: IncomeType[] = ["SALARY", "BONUS", "OTHER"];

interface FormErrors {
  payment_date?: string;
  income_type?: string;
  gross_amount?: string;
  social_insurance?: string;
  withholding_tax?: string;
  resident_tax?: string;
}

function IncomeFormContent() {
  const t = useTranslations("income.form");
  const tCommon = useTranslations("common");
  const tType = useTranslations("income.type");
  const tValidation = useTranslations("income.form.validation");
  const { user } = useUser();
  const router = useRouter();

  const [paymentDate, setPaymentDate] = useState("");
  const [incomeType, setIncomeType] = useState<IncomeType | "">("");
  const [grossAmount, setGrossAmount] = useState("");
  const [socialInsurance, setSocialInsurance] = useState("");
  const [withholdingTax, setWithholdingTax] = useState("");
  const [residentTax, setResidentTax] = useState("");

  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  function validate(): FormErrors {
    const errs: FormErrors = {};
    if (!paymentDate) errs.payment_date = tValidation("dateRequired");
    if (!incomeType) errs.income_type = tValidation("typeRequired");

    const gross = Number(grossAmount);
    if (!grossAmount) {
      errs.gross_amount = tValidation("grossRequired");
    } else if (gross <= 0) {
      errs.gross_amount = tValidation("grossPositive");
    }

    if (socialInsurance && Number(socialInsurance) < 0) {
      errs.social_insurance = tValidation("amountNonNegative");
    }
    if (withholdingTax && Number(withholdingTax) < 0) {
      errs.withholding_tax = tValidation("amountNonNegative");
    }
    if (residentTax && Number(residentTax) < 0) {
      errs.resident_tax = tValidation("amountNonNegative");
    }

    return errs;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    if (!user || !incomeType) return;

    setSubmitting(true);
    setSubmitError(null);

    try {
      await createIncomeEntry({
        user_id: user.id,
        payment_date: paymentDate,
        income_type: incomeType,
        gross_amount: Math.round(Number(grossAmount)),
        social_insurance: Math.round(Number(socialInsurance)) || 0,
        withholding_tax: Math.round(Number(withholdingTax)) || 0,
        resident_tax: Math.round(Number(residentTax)) || 0,
      });
      router.push("/income");
    } catch {
      setSubmitError(tCommon("error"));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="text-2xl font-bold">{t("title")}</h1>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <FormField id="payment-date" label={t("paymentDate")} error={errors.payment_date}>
          <input
            id="payment-date"
            type="date"
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
            aria-describedby={errors.payment_date ? "payment-date-error" : undefined}
            className={inputClass}
          />
        </FormField>

        <FormField id="income-type" label={t("incomeType")} error={errors.income_type}>
          <select
            id="income-type"
            value={incomeType}
            onChange={(e) => setIncomeType(e.target.value as IncomeType)}
            aria-describedby={errors.income_type ? "income-type-error" : undefined}
            className={inputClass}
          >
            <option value="">{t("selectType")}</option>
            {INCOME_TYPES.map((type) => (
              <option key={type} value={type}>
                {tType(type)}
              </option>
            ))}
          </select>
        </FormField>

        <FormField id="gross-amount" label={t("grossAmount")} error={errors.gross_amount}>
          <input
            id="gross-amount"
            type="number"
            min="1"
            step="1"
            value={grossAmount}
            onChange={(e) => setGrossAmount(e.target.value)}
            aria-describedby={errors.gross_amount ? "gross-amount-error" : undefined}
            className={inputClass}
          />
        </FormField>

        <FormField id="social-insurance" label={t("socialInsurance")} error={errors.social_insurance}>
          <input
            id="social-insurance"
            type="number"
            min="0"
            step="1"
            value={socialInsurance}
            onChange={(e) => setSocialInsurance(e.target.value)}
            aria-describedby={errors.social_insurance ? "social-insurance-error" : undefined}
            className={inputClass}
          />
        </FormField>

        <FormField id="withholding-tax" label={t("withholdingTax")} error={errors.withholding_tax}>
          <input
            id="withholding-tax"
            type="number"
            min="0"
            step="1"
            value={withholdingTax}
            onChange={(e) => setWithholdingTax(e.target.value)}
            aria-describedby={errors.withholding_tax ? "withholding-tax-error" : undefined}
            className={inputClass}
          />
        </FormField>

        <FormField id="resident-tax" label={t("residentTax")} error={errors.resident_tax}>
          <input
            id="resident-tax"
            type="number"
            min="0"
            step="1"
            value={residentTax}
            onChange={(e) => setResidentTax(e.target.value)}
            aria-describedby={errors.resident_tax ? "resident-tax-error" : undefined}
            className={inputClass}
          />
        </FormField>

        {submitError && (
          <p className="text-sm text-destructive">{submitError}</p>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? t("submitting") : t("submit")}
          </button>
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
          >
            {tCommon("cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function IncomeNewPage() {
  return (
    <RequireUser>
      <IncomeFormContent />
    </RequireUser>
  );
}
