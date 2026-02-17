"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { useUser } from "@/lib/user-context";
import {
  getTaxProfile,
  updateTaxProfile,
  getProfileDefinition,
  ApiError,
  type ProfileDefinitionResponse,
  type SchemaDefinition,
} from "@/lib/api-client";
import { inputClass } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";
import { RequireUser } from "@/components/shared/RequireUser";
import { FormSkeleton } from "@/components/shared/FormSkeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { FormField } from "@/components/shared/FormField";
import { DynamicFormRenderer } from "@/components/shared/DynamicFormRenderer";
import { InstructionSection } from "@/components/shared/InstructionSection";

interface FormErrors {
  dependents_count?: string;
  social_insurance_premium?: string;
  life_insurance_premium?: string;
  ideco_monthly_contribution?: string;
  [key: string]: string | undefined;
}

function ProfileFormContent() {
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i);

  const t = useTranslations("profile");
  const tCommon = useTranslations("common");
  const tValidation = useTranslations("profile.validation");
  const { user } = useUser();
  const { addToast } = useToast();
  const router = useRouter();
  const params = useParams();
  const year = Number(params.year);

  // Core field state
  const [hasSpouse, setHasSpouse] = useState(false);
  const [dependentsCount, setDependentsCount] = useState("");
  const [socialInsurancePremium, setSocialInsurancePremium] = useState("");
  const [lifeInsurancePremium, setLifeInsurancePremium] = useState("");
  const [idecoMonthlyContribution, setIdecoMonthlyContribution] = useState("");

  // Dynamic fields state
  const [additionalAttributes, setAdditionalAttributes] = useState<
    Record<string, unknown>
  >({});
  const [definition, setDefinition] = useState<ProfileDefinitionResponse | null>(
    null,
  );

  // UI state
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FormErrors>({});
  const [dynamicErrors, setDynamicErrors] = useState<Record<string, string>>(
    {},
  );
  const [submitting, setSubmitting] = useState(false);
  const [isNewProfile, setIsNewProfile] = useState(false);

  const fetchData = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setFetchError(null);
    setSubmitError(null);
    setIsNewProfile(false);

    try {
      // Fetch profile definition (may not exist for this year)
      let def: ProfileDefinitionResponse | null = null;
      try {
        def = await getProfileDefinition(year);
      } catch (err) {
        // 404 is expected — just means no dynamic fields for this year
        if (!(err instanceof ApiError && err.status === 404)) {
          throw err;
        }
      }
      setDefinition(def);

      // Fetch existing profile
      try {
        const profile = await getTaxProfile(user.id, year);
        setHasSpouse(profile.has_spouse);
        setDependentsCount(String(profile.dependents_count));
        setSocialInsurancePremium(String(profile.social_insurance_premium));
        setLifeInsurancePremium(String(profile.life_insurance_premium));
        setIdecoMonthlyContribution(String(profile.ideco_monthly_contribution));
        setAdditionalAttributes(profile.additional_attributes);
      } catch (err) {
        // 404 is expected — show empty form for creation
        if (!(err instanceof ApiError && err.status === 404)) {
          throw err;
        }
        setIsNewProfile(true);
        setHasSpouse(false);
        setDependentsCount("0");
        setSocialInsurancePremium("0");
        setLifeInsurancePremium("0");
        setIdecoMonthlyContribution("0");
        setAdditionalAttributes(
          def ? getDefaultAttributes(def.schema_definition) : {},
        );
      }
    } catch {
      setFetchError(tCommon("error"));
    } finally {
      setLoading(false);
    }
  }, [user, year, tCommon]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  function validate(): { core: FormErrors; dynamic: Record<string, string> } {
    const core: FormErrors = {};
    const dynamic: Record<string, string> = {};

    if (Number(dependentsCount) < 0) {
      core.dependents_count = tValidation("dependentsNonNegative");
    }
    if (Number(socialInsurancePremium) < 0) {
      core.social_insurance_premium = tValidation("amountNonNegative");
    }
    if (Number(lifeInsurancePremium) < 0) {
      core.life_insurance_premium = tValidation("amountNonNegative");
    }
    if (Number(idecoMonthlyContribution) < 0) {
      core.ideco_monthly_contribution = tValidation("amountNonNegative");
    }

    // Validate dynamic fields against schema
    if (definition?.schema_definition?.properties) {
      for (const [key, prop] of Object.entries(definition.schema_definition.properties)) {
        const val = additionalAttributes[key];
        if (
          (prop.type === "integer" || prop.type === "number") &&
          prop.minimum !== undefined &&
          typeof val === "number" &&
          val < prop.minimum
        ) {
          dynamic[key] = tValidation("amountNonNegative");
        }
      }
    }

    return { core, dynamic };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const { core, dynamic } = validate();
    setErrors(core);
    setDynamicErrors(dynamic);
    if (
      Object.keys(core).length > 0 ||
      Object.keys(dynamic).length > 0
    )
      return;
    if (!user) return;

    setSubmitting(true);
    setSubmitError(null);

    try {
      // Clean up dynamic attributes: round integers
      const cleanedAttrs: Record<string, unknown> = {};
      if (definition?.schema_definition?.properties) {
        for (const [key, prop] of Object.entries(definition.schema_definition.properties)) {
          const val = additionalAttributes[key];
          if (prop.type === "integer" && typeof val === "number") {
            cleanedAttrs[key] = Math.round(val);
          } else {
            cleanedAttrs[key] = val;
          }
        }
      }

      await updateTaxProfile(user.id, year, {
        has_spouse: hasSpouse,
        dependents_count: Math.round(Number(dependentsCount)) || 0,
        social_insurance_premium:
          Math.round(Number(socialInsurancePremium)) || 0,
        life_insurance_premium:
          Math.round(Number(lifeInsurancePremium)) || 0,
        ideco_monthly_contribution:
          Math.round(Number(idecoMonthlyContribution)) || 0,
        additional_attributes: cleanedAttrs,
      });
      addToast(t("saved"), "success");
      setIsNewProfile(false);
    } catch {
      setSubmitError(tCommon("error"));
    } finally {
      setSubmitting(false);
    }
  }

  function handleDynamicChange(key: string, value: unknown) {
    setAdditionalAttributes((prev) => ({ ...prev, [key]: value }));
  }

  function handleYearChange(newYear: number) {
    router.push(`/profile/${newYear}`);
  }

  if (loading) return <FormSkeleton fields={6} />;
  if (fetchError) return <ErrorState message={fetchError} onRetry={fetchData} />;

  return (
    <div className="mx-auto max-w-lg">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <div className="flex items-center gap-2">
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

      <InstructionSection title={t("instructions.title")}>
        <p>{t("instructions.body")}</p>
      </InstructionSection>

      {isNewProfile && (
        <p className="mb-4 text-sm text-muted-foreground">{t("notFound")}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Core fields section */}
        <fieldset>
          <legend className="mb-3 text-lg font-semibold">
            {t("coreFields")}
          </legend>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <input
                id="has-spouse"
                type="checkbox"
                checked={hasSpouse}
                onChange={(e) => setHasSpouse(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              <label htmlFor="has-spouse" className="text-sm font-medium">
                {t("field.hasSpouse")}
              </label>
            </div>

            <FormField
              id="dependents-count"
              label={t("field.dependentsCount")}
              error={errors.dependents_count}
            >
              <input
                id="dependents-count"
                type="number"
                min="0"
                step="1"
                value={dependentsCount}
                onChange={(e) => setDependentsCount(e.target.value)}
                aria-describedby={errors.dependents_count ? "dependents-count-error" : undefined}
                className={inputClass}
              />
            </FormField>

            <FormField
              id="social-insurance-premium"
              label={t("field.socialInsurancePremium")}
              error={errors.social_insurance_premium}
            >
              <input
                id="social-insurance-premium"
                type="number"
                min="0"
                step="1"
                value={socialInsurancePremium}
                onChange={(e) => setSocialInsurancePremium(e.target.value)}
                aria-describedby={errors.social_insurance_premium ? "social-insurance-premium-error" : undefined}
                className={inputClass}
              />
            </FormField>

            <FormField
              id="life-insurance-premium"
              label={t("field.lifeInsurancePremium")}
              error={errors.life_insurance_premium}
            >
              <input
                id="life-insurance-premium"
                type="number"
                min="0"
                step="1"
                value={lifeInsurancePremium}
                onChange={(e) => setLifeInsurancePremium(e.target.value)}
                aria-describedby={errors.life_insurance_premium ? "life-insurance-premium-error" : undefined}
                className={inputClass}
              />
            </FormField>

            <FormField
              id="ideco-monthly-contribution"
              label={t("field.idecoMonthlyContribution")}
              error={errors.ideco_monthly_contribution}
            >
              <input
                id="ideco-monthly-contribution"
                type="number"
                min="0"
                step="1"
                value={idecoMonthlyContribution}
                onChange={(e) => setIdecoMonthlyContribution(e.target.value)}
                aria-describedby={errors.ideco_monthly_contribution ? "ideco-monthly-contribution-error" : undefined}
                className={inputClass}
              />
            </FormField>
          </div>
        </fieldset>

        {/* Dynamic fields section */}
        {definition?.schema_definition && (
          <fieldset>
            <legend className="mb-3 text-lg font-semibold">
              {t("dynamicFields")}
            </legend>
            <DynamicFormRenderer
              schema={definition.schema_definition}
              values={additionalAttributes}
              errors={dynamicErrors}
              onChange={handleDynamicChange}
            />
          </fieldset>
        )}

        {!definition && !loading && (
          <p className="text-sm text-muted-foreground">{t("noDefinition")}</p>
        )}

        {submitError && (
          <p className="text-sm text-destructive">{submitError}</p>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? t("saving") : tCommon("save")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Extract default values from schema properties. */
function getDefaultAttributes(schema: SchemaDefinition): Record<string, unknown> {
  const attrs: Record<string, unknown> = {};
  if (!schema.properties) return attrs;

  for (const [key, prop] of Object.entries(schema.properties)) {
    if (prop.default !== undefined) {
      attrs[key] = prop.default;
    } else {
      switch (prop.type) {
        case "boolean":
          attrs[key] = false;
          break;
        case "integer":
        case "number":
          attrs[key] = 0;
          break;
        default:
          attrs[key] = "";
      }
    }
  }
  return attrs;
}

export default function ProfileYearPage() {
  return (
    <RequireUser>
      <ProfileFormContent />
    </RequireUser>
  );
}
