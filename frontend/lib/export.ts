// Client-side CSV export helper.
// Fetches the CSV text from the API (reusing the shared client for auth +
// error handling) and triggers a browser download without leaving the page.
import { api } from "./api";

export type ExportType = "clients" | "alerts";

/** Download the client book or alert list as a CSV file. */
export async function downloadExport(type: ExportType): Promise<void> {
  // The API returns text/csv; api.get falls back to the raw string when the
  // body is not JSON, so we receive the CSV verbatim.
  const csv = await api.get<string>(`/api/monitor/export?type=${type}`);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `kritifin-${type}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
