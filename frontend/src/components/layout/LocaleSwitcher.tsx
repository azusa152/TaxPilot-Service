"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter, usePathname } from "@/i18n/navigation";
import { routing, type Locale } from "@/i18n/routing";
import { useUser } from "@/lib/user-context";
import { useToast } from "@/lib/toast-context";

export function LocaleSwitcher() {
  const t = useTranslations("common.locale");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const { user, updateLocalePreference } = useUser();
  const { addToast } = useToast();

  function onLocaleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const nextLocale = e.target.value as Locale;
    router.replace(pathname, { locale: nextLocale });

    // Persist to backend if user is logged in
    if (user) {
      updateLocalePreference(nextLocale).catch(() => {
        addToast("Failed to save language preference", "error");
      });
    }
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="locale-select" className="text-sm text-muted-foreground">
        {t("switchLocale")}
      </label>
      <select
        id="locale-select"
        value={locale}
        onChange={onLocaleChange}
        className="rounded-md border bg-background px-2 py-1 text-sm"
      >
        {routing.locales.map((loc) => (
          <option key={loc} value={loc}>
            {t(loc)}
          </option>
        ))}
      </select>
    </div>
  );
}
