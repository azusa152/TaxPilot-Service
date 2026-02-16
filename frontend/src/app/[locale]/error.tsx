"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("common");

  useEffect(() => {
    // TODO: Replace with structured error tracking (e.g. Sentry) once available
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-4 py-16">
      <h2 className="text-lg font-semibold text-destructive">
        {t("error")}
      </h2>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        {t("errorBoundaryMessage")}
      </p>
      <button
        onClick={reset}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        {t("retry")}
      </button>
    </div>
  );
}
