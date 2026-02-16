"use client";

import { useTranslations } from "next-intl";
import { type SchemaDefinition } from "@/lib/api-client";
import { inputClass } from "@/lib/utils";
import { FormField } from "@/components/shared/FormField";

interface DynamicFormRendererProps {
  schema: SchemaDefinition;
  values: Record<string, unknown>;
  errors: Record<string, string>;
  onChange: (key: string, value: unknown) => void;
}

export function DynamicFormRenderer({
  schema,
  values,
  errors,
  onChange,
}: DynamicFormRendererProps) {
  const tDynamic = useTranslations("profile.dynamicFieldLabel");

  if (!schema.properties || Object.keys(schema.properties).length === 0) {
    return null;
  }

  function getLabel(key: string): string {
    if (tDynamic.has(key)) {
      return tDynamic(key);
    }
    // Fallback: convert snake_case to Title Case
    return key
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties!).map(([key, prop]) => {
        const value = values[key] ?? prop.default ?? getDefaultForType(prop.type);
        const error = errors[key];

        if (prop.type === "boolean") {
          return (
            <div key={key} className="flex items-center gap-3">
              <input
                id={`dynamic-${key}`}
                type="checkbox"
                checked={Boolean(value)}
                onChange={(e) => onChange(key, e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              <label htmlFor={`dynamic-${key}`} className="text-sm font-medium">
                {getLabel(key)}
              </label>
              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>
          );
        }

        if (prop.type === "integer" || prop.type === "number") {
          return (
            <FormField
              key={key}
              id={`dynamic-${key}`}
              label={getLabel(key)}
              error={error}
            >
              <input
                id={`dynamic-${key}`}
                type="number"
                min={prop.minimum}
                max={prop.maximum}
                step={prop.type === "integer" ? "1" : "any"}
                value={value as number}
                onChange={(e) => onChange(key, e.target.value === "" ? 0 : Number(e.target.value))}
                className={inputClass}
              />
            </FormField>
          );
        }

        if (prop.enum && prop.enum.length > 0) {
          return (
            <FormField
              key={key}
              id={`dynamic-${key}`}
              label={getLabel(key)}
              error={error}
            >
              <select
                id={`dynamic-${key}`}
                value={value as string}
                onChange={(e) => onChange(key, e.target.value)}
                className={inputClass}
              >
                <option value="">—</option>
                {/* TODO(F6): Localize enum option labels via translation keys */}
                {prop.enum.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </FormField>
          );
        }

        // Default: string input
        return (
          <FormField
            key={key}
            id={`dynamic-${key}`}
            label={getLabel(key)}
            error={error}
          >
            <input
              id={`dynamic-${key}`}
              type="text"
              value={(value as string) ?? ""}
              onChange={(e) => onChange(key, e.target.value)}
              className={inputClass}
            />
          </FormField>
        );
      })}
    </div>
  );
}

function getDefaultForType(type: string): unknown {
  switch (type) {
    case "boolean":
      return false;
    case "integer":
    case "number":
      return 0;
    default:
      return "";
  }
}
