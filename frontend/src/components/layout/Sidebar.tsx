"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { Home, Wallet, UserCircle, Upload, Calculator } from "lucide-react";

interface NavItem {
  href: string;
  labelKey: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { href: "/", labelKey: "home", icon: <Home className="h-4 w-4" /> },
  { href: "/income", labelKey: "income", icon: <Wallet className="h-4 w-4" /> },
  {
    href: "/profile",
    labelKey: "profile",
    icon: <UserCircle className="h-4 w-4" />,
  },
  {
    href: "/upload",
    labelKey: "upload",
    icon: <Upload className="h-4 w-4" />,
  },
  {
    href: "/calculate",
    labelKey: "calculate",
    icon: <Calculator className="h-4 w-4" />,
  },
];

export function Sidebar() {
  const t = useTranslations("common.nav");
  const pathname = usePathname();

  // TODO: Phase F6 — add mobile hamburger menu as an alternative to this sidebar
  return (
    <aside className="hidden w-56 shrink-0 border-r md:block">
      <nav className="flex flex-col gap-1 p-4">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {item.icon}
              {t(item.labelKey)}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
