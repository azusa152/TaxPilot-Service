"use client";

import { useTranslations } from "next-intl";

export function LoadingState() {
  const t = useTranslations("common");

  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex items-center gap-3 text-muted-foreground">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>{t("loading")}</span>
      </div>
    </div>
  );
}
