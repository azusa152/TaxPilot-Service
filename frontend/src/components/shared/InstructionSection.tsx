"use client";

import { useState } from "react";

export function InstructionSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mb-4 rounded-lg border bg-blue-50 dark:bg-blue-950/20">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between p-3 text-sm font-medium hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
        aria-expanded={open}
      >
        <span>{title}</span>
        <span className="text-lg">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 text-sm text-muted-foreground space-y-2">
          {children}
        </div>
      )}
    </div>
  );
}
