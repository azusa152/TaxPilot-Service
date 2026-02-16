import { useTranslations } from "next-intl";
import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "common" });

  return {
    title: t("welcome"),
    description: t("appDescription"),
  };
}

export default function HomePage() {
  const t = useTranslations("common");

  return (
    <div className="flex flex-col items-center justify-center py-16">
      <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
        {t("welcome")}
      </h1>
      <p className="mt-4 max-w-lg text-center text-muted-foreground">
        {t("welcomeSubtitle")}
      </p>
      <Link
        href="/income"
        className="mt-8 inline-flex items-center rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        {t("getStarted")}
      </Link>
    </div>
  );
}
