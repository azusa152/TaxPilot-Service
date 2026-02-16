"use client";

import { useTranslations } from "next-intl";

export default function NotFound() {
  const t = useTranslations("common");

  return (
    <div className="flex flex-col items-center justify-center py-16">
      <h1 className="text-2xl font-bold">404</h1>
      <p className="mt-2 text-muted-foreground">{t("notFound")}</p>
    </div>
  );
}
