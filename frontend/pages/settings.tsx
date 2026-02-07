import Head from "next/head";
import { useEffect, useState } from "react";
import { useLayout } from "../contexts/LayoutContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearMessage, setClearMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    setPageTitle("Settings");
    setHeaderExtra(null);
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra]);

  const handleClearData = () => {
    setClearing(true);
    setClearMessage(null);
    fetch(`${API_BASE}/api/settings/clear-data`, { method: "POST" })
      .then((res) => {
        if (!res.ok) return res.json().then((e) => Promise.reject(e.detail || res.statusText));
        return res.json();
      })
      .then(() => {
        setClearMessage({ type: "success", text: "All data cleared. You can re-upload documents and start fresh." });
        setShowClearConfirm(false);
      })
      .catch((e) => {
        setClearMessage({ type: "error", text: typeof e === "string" ? e : e?.message || "Failed to clear data" });
      })
      .finally(() => setClearing(false));
  };

  return (
    <>
      <Head><title>Settings – Jarvis</title></Head>
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-gray-600">
          Backend and API keys (OpenAI, Supabase, Qdrant) are configured via environment variables. No in-app settings are needed for this demo.
        </p>

        <section className="border-t border-gray-200 pt-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Data</h2>
          <p className="text-sm text-gray-500 mb-3">
            Remove all clients, alerts, ingested documents, and the vector index. Use this to reset the demo.
          </p>
          {clearMessage && (
            <p className={`text-sm mb-3 ${clearMessage.type === "success" ? "text-green-600" : "text-red-600"}`}>
              {clearMessage.text}
            </p>
          )}
          <button
            type="button"
            onClick={() => setShowClearConfirm(true)}
            className="px-4 py-2 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1"
          >
            Clear all data
          </button>
        </section>
      </div>

      {showClearConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => !clearing && setShowClearConfirm(false)}>
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md mx-4 border border-gray-200" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Clear all data?</h3>
            <p className="text-sm text-gray-600 mb-4">
              This will remove all clients, alerts, ingested documents, and the vector index. You cannot undo this.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => !clearing && setShowClearConfirm(false)}
                disabled={clearing}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleClearData}
                disabled={clearing}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {clearing ? "Clearing…" : "Clear all data"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
