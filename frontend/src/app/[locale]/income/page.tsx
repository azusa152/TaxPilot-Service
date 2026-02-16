"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useUser } from "@/lib/user-context";
import {
  listIncomeEntries,
  deleteIncomeEntry,
  type IncomeEntryResponse,
} from "@/lib/api-client";
import { formatJPY } from "@/lib/format";
import { RequireUser } from "@/components/shared/RequireUser";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { LoadingState } from "@/components/shared/LoadingState";
import { ErrorState } from "@/components/shared/ErrorState";
import { Trash2 } from "lucide-react";

function IncomeListContent() {
  const t = useTranslations("income");
  const tCommon = useTranslations("common");
  const tType = useTranslations("income.type");
  const { user } = useUser();

  const [entries, setEntries] = useState<IncomeEntryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchEntries = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listIncomeEntries(user.id);
      setEntries(data);
    } catch {
      setError(tCommon("error"));
    } finally {
      setLoading(false);
    }
  }, [user, tCommon]);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  async function handleDelete(entryId: number) {
    if (!user || !window.confirm(t("deleteConfirm"))) return;
    setDeletingId(entryId);
    try {
      await deleteIncomeEntry(user.id, entryId);
      setEntries((prev) => prev.filter((e) => e.id !== entryId));
    } catch {
      setError(tCommon("error"));
    } finally {
      setDeletingId(null);
    }
  }

  const columns: Column<IncomeEntryResponse>[] = [
    {
      key: "date",
      header: t("table.date"),
      render: (row) => row.payment_date ?? "—",
    },
    {
      key: "type",
      header: t("table.type"),
      render: (row) => (
        <span className="inline-flex rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
          {tType(row.income_type)}
        </span>
      ),
    },
    {
      key: "gross",
      header: t("table.gross"),
      render: (row) => formatJPY(row.gross_amount),
      className: "text-right",
    },
    {
      key: "socialInsurance",
      header: t("table.socialInsurance"),
      render: (row) => formatJPY(row.social_insurance),
      className: "text-right",
    },
    {
      key: "withholdingTax",
      header: t("table.withholdingTax"),
      render: (row) => formatJPY(row.withholding_tax),
      className: "text-right",
    },
    {
      key: "residentTax",
      header: t("table.residentTax"),
      render: (row) => formatJPY(row.resident_tax),
      className: "text-right",
    },
    {
      key: "actions",
      header: t("table.actions"),
      render: (row) =>
        deletingId === row.id ? (
          <span className="text-xs text-muted-foreground">{t("deleting")}</span>
        ) : (
          <button
            onClick={() => handleDelete(row.id)}
            className="rounded p-1 text-muted-foreground transition-colors hover:text-destructive"
            aria-label={`${tCommon("delete")} #${row.id}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ),
      className: "w-20",
    },
  ];

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetchEntries} />;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <Link
          href="/income/new"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          {t("addNew")}
        </Link>
      </div>

      <DataTable
        columns={columns}
        data={entries}
        keyExtractor={(row) => row.id}
        emptyMessage={t("empty")}
      />
    </div>
  );
}

export default function IncomePage() {
  return (
    <RequireUser>
      <IncomeListContent />
    </RequireUser>
  );
}
