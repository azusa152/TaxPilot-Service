"use client";

import { useTranslations } from "next-intl";
import { useToast, type ToastVariant } from "@/lib/toast-context";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

const variantStyles: Record<ToastVariant, string> = {
  success: "border-success bg-success/10 text-success-foreground",
  error: "border-destructive bg-destructive/10 text-destructive",
  info: "border-border bg-background text-foreground",
};

export function ToastContainer() {
  const t = useTranslations("common");
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 print:hidden"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg transition-all",
            variantStyles[toast.variant],
          )}
        >
          <p className="text-sm">{toast.message}</p>
          <button
            type="button"
            onClick={() => removeToast(toast.id)}
            className="ml-auto shrink-0 rounded-md p-1 opacity-70 transition-opacity hover:opacity-100"
            aria-label={t("close")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
