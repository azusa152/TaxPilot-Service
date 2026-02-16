import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "calculate" });

  return {
    title: t("title"),
  };
}

export default function CalculateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
