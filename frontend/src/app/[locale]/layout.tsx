import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations } from "next-intl/server";
import type { Metadata, Viewport } from "next";
import { routing } from "@/i18n/routing";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { Footer } from "@/components/layout/Footer";
import { UserProvider } from "@/lib/user-context";
import { ToastProvider } from "@/lib/toast-context";
import { ToastContainer } from "@/components/ui/ToastContainer";
import "@/app/globals.css";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "common" });

  const languages: Record<string, string> = {};
  for (const loc of routing.locales) {
    languages[loc] = `/${loc}`;
  }

  return {
    title: {
      template: `%s | ${t("appName")}`,
      default: t("appName"),
    },
    description: t("appDescription"),
    alternates: {
      canonical: `/${locale}`,
      languages,
    },
    openGraph: {
      title: t("appName"),
      description: t("appDescription"),
      locale,
      type: "website",
    },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!routing.locales.includes(locale as any)) {
    notFound();
  }

  const messages = await getMessages();
  const t = await getTranslations({ locale, namespace: "common" });

  return (
    <html lang={locale}>
      <body className="min-h-screen font-sans antialiased">
        <NextIntlClientProvider messages={messages}>
          <UserProvider>
            <ToastProvider>
              <div className="flex min-h-screen flex-col">
                <a
                  href="#main-content"
                  className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
                >
                  {t("skipToContent")}
                </a>
                <Header />
                <div className="flex flex-1">
                  <Sidebar />
                  <main id="main-content" className="flex-1 p-4 md:p-6">
                    {children}
                  </main>
                </div>
                <Footer />
              </div>
              <ToastContainer />
            </ToastProvider>
          </UserProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
