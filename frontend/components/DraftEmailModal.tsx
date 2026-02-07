"use client";

import React, { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type DraftEmailModalProps = {
  alertId: string | null;
  onClose: () => void;
  onMarkDone?: (alertId: string) => void;
};

export default function DraftEmailModal({ alertId, onClose, onMarkDone }: DraftEmailModalProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [markingDone, setMarkingDone] = useState(false);
  const canMarkDone = alertId != null && !alertId.startsWith("review-overdue-") && !!onMarkDone;

  useEffect(() => {
    if (!alertId) {
      setDraft(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    setDraft(null);
    fetch(`${API_BASE}/api/monitor/draft-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alert_id: alertId }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((e) => Promise.reject(e.detail || res.statusText));
        return res.json();
      })
      .then((data) => {
        setDraft(data.draft ?? "");
      })
      .catch((e) => {
        setError(typeof e === "string" ? e : e?.message || "Failed to generate draft");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [alertId]);

  const handleCopy = () => {
    if (!draft) return;
    navigator.clipboard.writeText(draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleMarkDone = () => {
    if (!alertId || !onMarkDone) return;
    setMarkingDone(true);
    fetch(`${API_BASE}/api/monitor/alerts/${encodeURIComponent(alertId)}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "COMPLETED" }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((e) => Promise.reject(e));
        onMarkDone(alertId);
        onClose();
      })
      .catch((e) => setError(Array.isArray(e?.detail) ? e.detail.map((x: { msg?: string }) => x.msg).join(", ") : e?.detail ?? "Failed to mark as done"))
      .finally(() => setMarkingDone(false));
  };

  if (alertId == null) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border border-gray-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Email draft</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="max-h-[60vh] overflow-auto px-6 py-4">
          {loading && <p className="text-sm text-gray-500">Generating draft…</p>}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
          )}
          {draft && !loading && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{draft}</pre>
          )}
        </div>
        <div className="flex flex-wrap justify-end gap-2 border-t border-gray-100 px-6 py-4">
          {canMarkDone && (
            <button
              type="button"
              onClick={handleMarkDone}
              disabled={markingDone}
              className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
            >
              {markingDone ? "Updating…" : "Mark as done"}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Close
          </button>
          {draft && (
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
            >
              {copied ? "Copied" : "Copy to clipboard"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
