"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getHealth } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type DisplayStatus = "healthy" | "degraded" | "offline";

function toDisplayStatus(apiStatus: string): DisplayStatus {
  if (apiStatus === "healthy") return "healthy";
  if (apiStatus === "degraded") return "degraded";
  return "offline";
}

export function HealthIndicator() {
  const t = useTranslations("common.footer");
  const [status, setStatus] = useState<DisplayStatus>("offline");

  useEffect(() => {
    let mounted = true;

    async function check() {
      try {
        const data = await getHealth();
        if (mounted) setStatus(toDisplayStatus(data.status));
      } catch {
        if (mounted) setStatus("offline");
      }
    }

    check();
    const interval = setInterval(check, 30_000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const dotColor: Record<DisplayStatus, string> = {
    healthy: "bg-green-500",
    degraded: "bg-yellow-500",
    offline: "bg-red-500",
  };

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span>{t("status")}:</span>
      <span
        className={cn("inline-block h-2 w-2 rounded-full", dotColor[status])}
        aria-label={t(status)}
      />
      <span>{t(status)}</span>
    </div>
  );
}
