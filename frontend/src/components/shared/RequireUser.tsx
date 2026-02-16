"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "@/i18n/navigation";
import { useUser } from "@/lib/user-context";
import { LoadingState } from "./LoadingState";

export function RequireUser({ children }: { children: ReactNode }) {
  const { user, loading } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/onboarding");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return <LoadingState />;
  }

  return <>{children}</>;
}
