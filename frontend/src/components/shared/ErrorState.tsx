"use client";

import { useTranslations } from "next-intl";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  const t = useTranslations("common");

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16">
      <p className="text-destructive">{message ?? t("error")}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          {t("retry")}
        </button>
      )}
    </div>
  );
}
