import Head from "next/head";
import { useEffect, useState } from "react";
import { Trash2, User, Building2, ShieldCheck } from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";
import { Card, CardHeader, Button, Modal, useToast } from "../components/ui";
import { useClearData } from "../hooks/useApi";

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
        <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-600">
          {icon}
        </span>
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
          <p className="mt-0.5 text-sm text-gray-500">{description}</p>
        </div>
      </div>
      {children && <div className="flex-shrink-0">{children}</div>}
    </div>
  );
}

export default function SettingsPage() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const { notify } = useToast();
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const clearData = useClearData();

  useEffect(() => {
    setPageTitle("Settings");
    setHeaderExtra(null);
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra]);

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
        <title>Settings — Jarvis</title>
      </Head>

      <p className="mb-8 max-w-2xl text-sm leading-relaxed text-gray-500">
        Manage your account, workspace, and data. API keys for the AI provider,
        database, and vector store are configured securely on the server.
      </p>

      <div className="max-w-3xl space-y-6">
        <Card>
          <CardHeader title="Account" />
          <div className="divide-y divide-gray-100">
            <SettingRow
              icon={<User className="h-4 w-4" aria-hidden />}
              title="Profile"
              description="Your name and email. Account management arrives with sign-in."
            >
              <Button variant="secondary" size="sm" disabled>
                Coming soon
              </Button>
            </SettingRow>
            <SettingRow
              icon={<Building2 className="h-4 w-4" aria-hidden />}
              title="Workspace"
              description="Firm details and team members for shared client books."
            >
              <Button variant="secondary" size="sm" disabled>
                Coming soon
              </Button>
            </SettingRow>
          </div>
        </Card>

        <Card>
          <CardHeader title="Data & privacy" />
          <div className="divide-y divide-gray-100">
            <SettingRow
              icon={<ShieldCheck className="h-4 w-4" aria-hidden />}
              title="Data export"
              description="Download your clients, alerts, and documents (portability)."
            >
              <Button variant="secondary" size="sm" disabled>
                Coming soon
              </Button>
            </SettingRow>
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
      </div>

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
        <p className="mb-4 text-sm text-gray-600">
          This will remove all clients, alerts, ingested documents, and the
          vector index. You cannot undo this. Type{" "}
          <span className="font-semibold text-gray-900">DELETE</span> to confirm.
        </p>
        <input
          type="text"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="DELETE"
          aria-label="Type DELETE to confirm"
          className="w-full rounded-lg border border-gray-200 px-4 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
        />
      </Modal>
    </>
  );
}
