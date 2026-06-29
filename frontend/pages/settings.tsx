import Head from "next/head";
import { useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { Card, CardHeader, Button, Modal, useToast, PageIntro, PageShell } from "../components/ui";
import { usePageSetup } from "../hooks/usePageSetup";
import { useClearData, useExportData } from "../hooks/useApi";
import type { ExportType } from "../lib/export";

function SettingRow({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600 ring-1 ring-slate-200/80">
          {icon}
        </span>
        <div>
          <h3 className="text-sm font-semibold text-slate-950">{title}</h3>
          <p className="mt-0.5 text-sm leading-relaxed text-slate-500">{description}</p>
        </div>
      </div>
      {children && <div className="flex-shrink-0">{children}</div>}
    </div>
  );
}

export default function SettingsPage() {
  const { notify } = useToast();
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const clearData = useClearData();
  const exportData = useExportData();

  usePageSetup("Settings");

  const handleExport = (type: ExportType) => {
    exportData.mutate(type, {
      onSuccess: () => notify(`Exported ${type} as CSV.`, "success"),
      onError: (e: unknown) =>
        notify(e instanceof Error ? e.message : "Export failed", "error"),
    });
  };

  const handleClearData = () => {
    clearData.mutate(undefined, {
      onSuccess: () => {
        notify("All data cleared. You can re-upload documents and start fresh.", "success");
        setShowClearConfirm(false);
        setConfirmText("");
      },
      onError: (e: unknown) =>
        notify(e instanceof Error ? e.message : "Failed to clear data", "error"),
    });
  };

  return (
    <>
      <Head>
        <title>Settings - KritiFin</title>
      </Head>

      <PageShell>
      <PageIntro>
        Manage your workspace and data. Provider keys are configured securely on the server.
      </PageIntro>

      <div className="max-w-3xl space-y-6" data-testid="settings-page">
        <Card>
          <CardHeader title="Data export" />
          <div className="divide-y divide-slate-100">
            <SettingRow
              icon={<Download className="h-4 w-4" aria-hidden />}
              title="Export your data"
              description="Download your client book or alert list as a CSV file for spreadsheets, reporting, or backup."
            >
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleExport("clients")}
                  loading={exportData.isPending && exportData.variables === "clients"}
                  data-testid="export-clients-button"
                >
                  Export clients
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleExport("alerts")}
                  loading={exportData.isPending && exportData.variables === "alerts"}
                  data-testid="export-alerts-button"
                >
                  Export alerts
                </Button>
              </div>
            </SettingRow>
          </div>
        </Card>

        <Card>
          <CardHeader title="Data & privacy" />
          <div className="divide-y divide-slate-100">
            <SettingRow
              icon={<Trash2 className="h-4 w-4" aria-hidden />}
              title="Clear all data"
              description="Permanently remove all clients, alerts, ingested documents, and the vector index. This cannot be undone."
            >
              <Button variant="danger" size="sm" onClick={() => setShowClearConfirm(true)}>
                Clear all data
              </Button>
            </SettingRow>
          </div>
        </Card>

        <p className="text-sm text-slate-500">
          Profile and workspace settings are available in the production release.
        </p>
      </div>
      </PageShell>

      <Modal
        open={showClearConfirm}
        onClose={() => !clearData.isPending && setShowClearConfirm(false)}
        title="Clear all data?"
        size="md"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setShowClearConfirm(false)}
              disabled={clearData.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleClearData}
              loading={clearData.isPending}
              disabled={confirmText !== "DELETE"}
              className="bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
            >
              Clear all data
            </Button>
          </>
        }
      >
        <p className="mb-4 text-sm leading-relaxed text-slate-600">
          This will remove all clients, alerts, ingested documents, and the
          vector index. You cannot undo this. Type{" "}
          <span className="font-semibold text-slate-950">DELETE</span> to confirm.
        </p>
        <input
          type="text"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="DELETE"
          aria-label="Type DELETE to confirm"
          className="input"
        />
      </Modal>
    </>
  );
}
