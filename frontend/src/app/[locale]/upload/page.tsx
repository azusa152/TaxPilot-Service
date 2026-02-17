"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useUser } from "@/lib/user-context";
import {
  uploadDocument,
  ApiError,
  type IncomeEntryResponse,
} from "@/lib/api-client";
import { formatJPY } from "@/lib/format";
import { RequireUser } from "@/components/shared/RequireUser";
import { FileUpload } from "@/components/shared/FileUpload";
import { InstructionSection } from "@/components/shared/InstructionSection";

function UploadContent() {
  const t = useTranslations("upload");
  const tError = useTranslations("upload.error");
  const tResult = useTranslations("upload.result");
  const tType = useTranslations("income.type");
  const { user } = useUser();

  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IncomeEntryResponse | null>(null);

  async function handleFileSelected(file: File) {
    if (!user) return;
    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const entry = await uploadDocument(user.id, file);
      setResult(entry);
    } catch (err) {
      if (err instanceof ApiError && err.errorCode === "UNSUPPORTED_FILE_TYPE") {
        setError(tError("unsupportedType"));
      } else {
        setError(tError("uploadFailed"));
      }
    } finally {
      setUploading(false);
    }
  }

  function handleValidationError(message: string) {
    setError(message);
  }

  function handleUploadAnother() {
    setResult(null);
    setError(null);
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="mb-6 text-2xl font-bold">{t("title")}</h1>

      <InstructionSection title={t("instructions.title")}>
        <p>{t("instructions.body")}</p>
      </InstructionSection>

      {!result && (
        <>
          <FileUpload
            onFileSelected={handleFileSelected}
            onValidationError={handleValidationError}
            disabled={uploading}
          />

          {uploading && (
            <div className="mt-4 flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <p className="text-sm text-muted-foreground">{t("processing")}</p>
            </div>
          )}

          {error && (
            <p className="mt-4 text-sm text-destructive">{error}</p>
          )}
        </>
      )}

      {result && (
        <div className="space-y-4">
          <p className="text-sm text-success">{t("success")}</p>

          <div className="rounded-lg border p-4">
            <h2 className="mb-3 text-lg font-semibold">{tResult("title")}</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{tResult("sourceFile")}</dt>
                <dd className="font-medium">{result.source_file ?? "—"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{tResult("incomeType")}</dt>
                <dd>
                  <span className="inline-flex rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                    {tType(result.income_type)}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{tResult("grossAmount")}</dt>
                <dd className="font-medium">
                  {result.gross_amount > 0
                    ? formatJPY(result.gross_amount)
                    : tResult("pending")}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{tResult("paymentDate")}</dt>
                <dd className="font-medium">
                  {result.payment_date ?? tResult("pending")}
                </dd>
              </div>
            </dl>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/income"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              {t("viewAllEntries")}
            </Link>
            <button
              type="button"
              onClick={handleUploadAnother}
              className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
            >
              {t("uploadAnother")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function UploadPage() {
  return (
    <RequireUser>
      <UploadContent />
    </RequireUser>
  );
}
