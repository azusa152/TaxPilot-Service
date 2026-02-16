"use client";

import { useTranslations } from "next-intl";
import { LocaleSwitcher } from "./LocaleSwitcher";

export function Header() {
  const t = useTranslations("common");

  return (
    <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-14 items-center px-4 md:px-6">
        <div className="flex items-center gap-2 font-semibold">
          <span className="text-lg">{t("appName")}</span>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <LocaleSwitcher />
        </div>
      </div>
    </header>
  );
}
