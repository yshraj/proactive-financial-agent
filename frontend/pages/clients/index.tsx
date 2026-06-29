import Head from "next/head";
import Link from "next/link";
import { Upload, Users, Sparkles } from "lucide-react";
import {
  Card,
  CardHeader,
  ButtonLink,
  EmptyState,
  ErrorState,
  TableSkeleton,
  PageIntro,
  PageShell,
} from "../../components/ui";
import { usePageSetup } from "../../hooks/usePageSetup";
import { useBookAnalytics, useClients } from "../../hooks/useApi";
import { errorMessage } from "../../lib/api";
import { formatCurrency, formatDate, formatRiskScore } from "../../lib/format";
import { clientDetail, ROUTES } from "../../lib/routes";
import { chatWithQuery, DEMO_COPILOT_QUERY } from "../../lib/demo";

export default function ClientsPage() {
  const clientsQuery = useClients();
  const analyticsQuery = useBookAnalytics();
  const clients = clientsQuery.data?.clients ?? [];
  const analytics = analyticsQuery.data;

  usePageSetup(
    "Clients",
    clients.length > 0 ? (
      <ButtonLink
        href={chatWithQuery(DEMO_COPILOT_QUERY)}
        leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
      >
        Ask AI Copilot
      </ButtonLink>
    ) : null,
    [clients.length]
  );

  return (
    <>
      <Head>
        <title>Clients - KritiFin</title>
      </Head>

      <PageShell wide>
      <PageIntro>
        Browse your client book — profile snapshots, open alerts, and AI summaries in one place.
      </PageIntro>

      {analytics && clients.length > 0 && (
        <div
          className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4"
          data-testid="book-analytics"
        >
          {[
            { label: "Clients", value: String(analytics.clients_total) },
            { label: "Assets under advice", value: formatCurrency(analytics.total_aum) },
            {
              label: "Average risk",
              value: formatRiskScore(analytics.average_risk_score),
            },
            { label: "Reviews overdue", value: String(analytics.reviews_overdue) },
          ].map(({ label, value }) => (
            <Card key={label} className="p-4">
              <p className="ui-label">{label}</p>
              <p className="mt-2 text-xl font-semibold tabular-nums text-slate-950">{value}</p>
            </Card>
          ))}
        </div>
      )}

      {clientsQuery.isError && (
        <ErrorState
          message={errorMessage(clientsQuery.error)}
          onRetry={() => clientsQuery.refetch()}
        />
      )}

      {!clientsQuery.isError && (
        <Card className="overflow-hidden" data-testid="clients-list-page">
          <CardHeader
            title="All clients"
            description={
              clientsQuery.isLoading
                ? "Loading…"
                : `${clients.length} client${clients.length !== 1 ? "s" : ""} in your book`
            }
          />
          {clientsQuery.isLoading ? (
            <TableSkeleton rows={6} />
          ) : clients.length === 0 ? (
            <EmptyState
              icon={<Users className="h-5 w-5" aria-hidden />}
              title="No clients yet"
              description="Upload fact-finds and meeting notes in Ingestion to build your client book."
              action={
                <ButtonLink href={ROUTES.ingestion} leftIcon={<Upload className="h-4 w-4" aria-hidden />}>
                  Go to Ingestion
                </ButtonLink>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50/60">
                    {["Client", "Last review", "Assets", "Risk", "Open alerts", ""].map((h, i) => (
                      <th
                        key={h || i}
                        className={`px-6 py-3 text-xs font-medium text-gray-500 ${i === 5 ? "text-right" : "text-left"}`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {clients.map((client) => (
                    <tr
                      key={client.id}
                      className="border-b border-gray-100 last:border-0 transition-colors hover:bg-gray-50/70"
                    >
                      <td className="px-6 py-4 font-medium text-gray-900">
                        <Link
                          href={clientDetail(client.id)}
                          className="text-brand-700 hover:text-brand-800 hover:underline"
                          data-testid={`client-link-${client.id}`}
                        >
                          {client.full_name}
                        </Link>
                      </td>
                      <td className="px-6 py-4 text-gray-600">
                        {client.last_review_date ? formatDate(client.last_review_date) : "—"}
                      </td>
                      <td className="px-6 py-4 tabular-nums text-gray-600">
                        {formatCurrency(client.total_assets)}
                      </td>
                      <td className="px-6 py-4 text-gray-600">
                        {formatRiskScore(client.risk_score)}
                      </td>
                      <td className="px-6 py-4 tabular-nums text-gray-600">
                        {client.open_alert_count ?? 0}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Link
                          href={clientDetail(client.id)}
                          className="text-sm font-medium text-brand-600 hover:text-brand-700"
                        >
                          View →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      </PageShell>
    </>
  );
}
