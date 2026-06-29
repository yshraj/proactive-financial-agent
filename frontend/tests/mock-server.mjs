// Self-contained mock backend for frontend E2E tests.
// It mirrors the FastAPI response shapes used by the UI without requiring
// Supabase, Qdrant, or OpenAI credentials.
import { createServer } from "node:http";

const apiUrl = new URL(process.env.PLAYWRIGHT_API_URL || "http://localhost:8000");
const PORT = process.env.MOCK_PORT ? Number(process.env.MOCK_PORT) : Number(apiUrl.port || 8000);
const iso = (d) => d.toISOString().slice(0, 10);
const today = new Date();
const plus = (n) => {
  const d = new Date(today);
  d.setDate(d.getDate() + n);
  return iso(d);
};

const CLIENTS = [
  { id: "c1", full_name: "Alan & Lynne Partridge" },
  { id: "c2", full_name: "David & Sarah Chen" },
  { id: "c3", full_name: "Priya & Anil Sharma" },
  { id: "c4", full_name: "Michael & Sarah Thompson" },
  { id: "c5", full_name: "The Williams Family" },
  { id: "c6", full_name: "Jackson Holdings Ltd" },
];

const ALERTS = [
  { id: "a1", client_id: "c1", client_name: "Alan & Lynne Partridge", trigger_date: plus(3), type: "DEADLINE", priority: "HIGH", title: "Next review due", description: "Scheduled annual review 09:30, Office. Prepare cashflow update.", status: "PENDING" },
  { id: "a2", client_id: "c2", client_name: "David & Sarah Chen", trigger_date: plus(6), type: "OPPORTUNITY", priority: "MEDIUM", title: "ISA allowance unused", description: "£20,000 ISA allowance still available this tax year.", status: "PENDING" },
  { id: "a3", client_id: "c3", client_name: "Priya & Anil Sharma", trigger_date: plus(9), type: "COMPLIANCE", priority: "HIGH", title: "Wills update strong priority", description: "LPAs not in place; estate planning gap flagged.", status: "PENDING" },
  { id: "a4", client_id: "c4", client_name: "Michael & Sarah Thompson", trigger_date: plus(12), type: "DEADLINE", priority: "MEDIUM", title: "Mortgage fixed-rate ends", description: "Remortgage planning required.", status: "PENDING" },
  { id: "a5", client_id: "c5", client_name: "The Williams Family", trigger_date: plus(15), type: "OPPORTUNITY", priority: "LOW", title: "Client DOB check-in", description: "Annual birthday check-in.", status: "PENDING" },
];
const REVIEW_OVERDUE = [
  { id: "review-overdue-c5", client_id: "c5", client_name: "The Williams Family", trigger_date: iso(today), type: "REVIEW_OVERDUE", priority: "HIGH", title: "Annual review overdue", description: "No review in 12+ months.", status: "PENDING" },
];
const OVERDUE_FOLLOW_UPS = [
  { id: "f1", client_id: "c1", client_name: "Alan & Lynne Partridge", trigger_date: plus(-8), type: "FOLLOW_UP", priority: "MEDIUM", title: "Waiting on client: pension decision", description: "Alan to decide on pension contribution increase.", status: "PENDING" },
  { id: "f2", client_id: "c3", client_name: "Priya & Anil Sharma", trigger_date: plus(-21), type: "FOLLOW_UP", priority: "HIGH", title: "Waiting on client: signed LOA", description: "Awaiting signed letter of authority.", status: "PENDING" },
];
const COMPLETED = [
  { id: "done1", client_id: "c2", client_name: "David & Sarah Chen", trigger_date: plus(-4), type: "DEADLINE", priority: "MEDIUM", title: "Sent fund switch confirmation", description: "", status: "COMPLETED" },
];
const DOCUMENTS = [
  { id: "d1", filename: "Partridge_FactFind_2026.pdf", content_hash: "ab12", file_size_bytes: 184320, uploaded_at: iso(today) + "T09:30:00" },
  { id: "d2", filename: "Chen_MeetingNotes_Jan.docx", content_hash: "cd34", file_size_bytes: 45056, uploaded_at: plus(-2) + "T14:05:00" },
];

const CLIENT_DETAILS = {
  c1: {
    id: "c1",
    full_name: "Alan & Lynne Partridge",
    last_review_date: plus(-400),
    retirement_target_age: 65,
    risk_score: 5,
    total_assets: 895000,
    cash_savings: 62000,
    raw_profile_json: null,
    pending_alerts: [ALERTS[0]],
    overdue_follow_ups: OVERDUE_FOLLOW_UPS.filter((a) => a.client_id === "c1"),
    document_count: 1,
    summary:
      "Alan & Lynne Partridge last reviewed over a year ago with £895k assets. Priority: annual review in 3 days and pension contribution decision.",
    planning_completeness: { score: 100, missing: [] },
    at_risk: { score: 65, level: "MEDIUM", rationale: "review overdue (13 months); 1 overdue follow-up(s)" },
    next_best_actions: [
      { action: "Book the annual review", reason: "Review is overdue — Consumer Duty expects ongoing-service evidence.", priority: "HIGH" },
      { action: "Chase: Waiting on client: pension decision", reason: "Follow-up is past its due date.", priority: "HIGH" },
    ],
  },
  c2: {
    id: "c2",
    full_name: "David & Sarah Chen",
    last_review_date: plus(-120),
    retirement_target_age: 60,
    risk_score: 6,
    total_assets: 620000,
    cash_savings: 62000,
    raw_profile_json: null,
    pending_alerts: [ALERTS[1]],
    overdue_follow_ups: [],
    document_count: 1,
    summary:
      "David & Sarah Chen have unused ISA allowance and strong cash holdings. Follow up on tax-year planning.",
  },
};

const CLIENTS_ENRICHED = CLIENTS.map((c) => ({
  ...c,
  last_review_date: CLIENT_DETAILS[c.id]?.last_review_date ?? plus(-200),
  total_assets: CLIENT_DETAILS[c.id]?.total_assets ?? 500000,
  risk_score: CLIENT_DETAILS[c.id]?.risk_score ?? 5,
  open_alert_count: ALERTS.filter((a) => a.client_id === c.id).length,
}));

const DIGEST =
  "Good morning. Start with Alan & Lynne Partridge — their annual review is due in 3 days and a pension decision is outstanding. Priya & Anil Sharma needs a signed LOA chased (21 days overdue). The Williams Family review is also overdue under Consumer Duty.";

const CHAT_ANSWER =
  "Based on your records, **David & Sarah Chen** have £20,000 of unused ISA allowance [1] and **The Williams Family** have about £8,500 remaining. Prioritise the Chens given their cash holdings.";
const CHAT_SOURCES = [
  {
    ref: 1,
    content: "Joint Savings: £62,000 easy access. Discussed using ISA allowance...",
    client_name: "David & Sarah Chen",
    doc_type: "Meeting notes",
    date: plus(-2),
    relevance: 0.72,
  },
];
const BRIEF =
  "## Alan & Lynne Partridge\n\n### Client Snapshot\n- Total assets: **£895,000**; risk score **5/10**.\n\n### Upcoming Reviews\n- **Next review due in 3 days**.\n\n### Action Checklist\n- Alan to decide on pension contribution increase.";
const TALKING_POINTS = [
  "Pension contribution increase: recap recommendation",
  "Remortgage planning: confirm timeline before May 2026",
];

function send(res, code, payload) {
  res.writeHead(code, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,X-API-Key,Authorization",
  });
  res.end(JSON.stringify(payload));
}

const server = createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;
  if (req.method === "OPTIONS") return send(res, 200, {});

  if (req.method === "GET") {
    if (path === "/health") return send(res, 200, { status: "ok" });
    if (path === "/api/monitor/export") {
      const type = url.searchParams.get("type") === "alerts" ? "alerts" : "clients";
      const csv =
        type === "alerts"
          ? "Client,Trigger date,Type,Priority,Status,Title,Description\r\nAlan & Lynne Partridge," +
            plus(3) +
            ",DEADLINE,HIGH,PENDING,Next review due,Scheduled annual review\r\n"
          : "Name,Last review,Total assets,Cash savings,Risk score,Retirement target age,Open alerts\r\nAlan & Lynne Partridge," +
            plus(-400) +
            ",895000,62000,5,65,1\r\n";
      res.writeHead(200, {
        "Content-Type": "text/csv",
        "Content-Disposition": `attachment; filename="kritifin-${type}.csv"`,
        "Access-Control-Allow-Origin": "*",
      });
      return res.end(csv);
    }
    if (path === "/api/monitor/pulse") {
      const alerts = [...ALERTS, ...REVIEW_OVERDUE];
      return send(res, 200, {
        alerts,
        total: alerts.length,
        high_risk: alerts.filter((a) => a.priority === "HIGH").length,
        deadlines: alerts.filter((a) => a.type === "DEADLINE").length,
        client_count: CLIENTS.length,
        overdue_follow_ups: OVERDUE_FOLLOW_UPS,
      });
    }
    if (path === "/api/monitor/completed") return send(res, 200, { alerts: COMPLETED });
    if (path === "/api/monitor/clients") return send(res, 200, { clients: CLIENTS_ENRICHED });
    if (path === "/api/monitor/playbooks")
      return send(res, 200, {
        playbooks: [
          { id: "annual_review", name: "Annual review preparation", description: "Prep and run a review.", task_count: 3 },
          { id: "new_client_onboarding", name: "New client onboarding", description: "Onboard a new client.", task_count: 3 },
        ],
      });
    if (path === "/api/monitor/analytics")
      return send(res, 200, {
        clients_total: CLIENTS.length,
        total_aum: CLIENTS_ENRICHED.reduce((sum, c) => sum + (c.total_assets || 0), 0),
        average_risk_score: 5,
        reviews_overdue: 2,
      });
    if (path.startsWith("/api/monitor/clients/")) {
      const id = path.split("/").pop();
      const detail = CLIENT_DETAILS[id];
      if (!detail) return send(res, 404, { detail: "Client not found" });
      return send(res, 200, detail);
    }
    if (path === "/api/monitor/digest") {
      return send(res, 200, { digest: DIGEST, generated_at: new Date().toISOString() });
    }
    if (path === "/api/monitor/alerts")
      return send(res, 200, { alerts: [...ALERTS, ...REVIEW_OVERDUE, ...OVERDUE_FOLLOW_UPS] });
    if (path === "/api/ingest/documents") return send(res, 200, DOCUMENTS);
    if (path === "/api/ingest/note-templates")
      return send(res, 200, {
        templates: [
          { id: "discovery", name: "Discovery meeting", section_count: 5 },
          { id: "annual_review", name: "Annual review", section_count: 6 },
        ],
      });
    if (/^\/api\/ingest\/note-templates\/[^/]+$/.test(path)) {
      const id = path.split("/").pop();
      return send(res, 200, {
        id,
        name: "Annual review",
        markdown: "# Annual review\n\n## Changes since last review\n\n- \n",
      });
    }
    if (/^\/api\/ingest\/jobs\/[^/]+$/.test(path)) {
      const jobId = path.split("/").pop();
      return send(res, 200, {
        id: jobId,
        kind: "upload",
        filename: "sample.pdf",
        status: "DONE",
        progress: 100,
        message: "Done",
        document_id: jobId,
        error: null,
      });
    }
    if (path === "/api/compliance/audit")
      return send(res, 200, {
        entries: [
          {
            id: 2,
            kind: "review_note",
            timestamp: new Date().toISOString(),
            client_id: "c1",
            client_name: "Alan & Lynne Partridge",
            model: "gpt-4o-mini",
            preview: "# Client review note — Alan & Lynne Partridge …",
            ai_generated: false,
            reviewed: false,
            reviewed_at: null,
          },
        ],
      });
    return send(res, 404, { detail: "not found" });
  }

  let rawBody = "";
  req.on("data", (chunk) => {
    rawBody += chunk;
  });
  req.on("end", () => {
    if (req.method === "PATCH") {
      // Client profile edit: PATCH /api/monitor/clients/{id}
      const clientMatch = path.match(/^\/api\/monitor\/clients\/([^/]+)$/);
      if (clientMatch) {
        let body = {};
        try {
          body = rawBody ? JSON.parse(rawBody) : {};
        } catch {
          body = {};
        }
        const id = clientMatch[1];
        const base = CLIENT_DETAILS[id] ?? { id, full_name: "Client" };
        return send(res, 200, {
          id,
          full_name: body.full_name ?? base.full_name,
          last_review_date: body.last_review_date ?? base.last_review_date ?? null,
          retirement_target_age:
            body.retirement_target_age ?? base.retirement_target_age ?? null,
          risk_score: body.risk_score ?? base.risk_score ?? null,
          total_assets: body.total_assets ?? base.total_assets ?? null,
          cash_savings: body.cash_savings ?? base.cash_savings ?? null,
        });
      }
      // Alert status update: PATCH /api/monitor/alerts/{id}/status
      return send(res, 200, { ...ALERTS[0], status: "COMPLETED" });
    }
    if (/^\/api\/monitor\/clients\/[^/]+\/apply-playbook$/.test(path))
      return send(res, 200, { applied: 3 });
    if (/^\/api\/compliance\/audit\/[^/]+\/approve$/.test(path)) {
      const id = Number(path.split("/")[4]);
      return send(res, 200, {
        id,
        kind: "review_note",
        timestamp: new Date().toISOString(),
        client_id: "c1",
        client_name: "Alan & Lynne Partridge",
        model: "gpt-4o-mini",
        preview: "# Client review note …",
        ai_generated: false,
        reviewed: true,
        reviewed_at: new Date().toISOString(),
      });
    }
    if (/^\/api\/monitor\/clients\/[^/]+\/review-note$/.test(path))
      return send(res, 200, {
        note:
          "# Client review note — Alan & Lynne Partridge\n\n## Summary\nReview overdue; £895k assets.\n\n## Open items\n- Annual review overdue\n\n## Consumer Duty\n- Ongoing value to confirm.\n\nDraft for adviser review — confirm before filing.",
        generated_at: new Date().toISOString(),
        ai_generated: false,
      });
    if (path === "/api/chat") {
      let body = {};
      try {
        body = rawBody ? JSON.parse(rawBody) : {};
      } catch {
        body = {};
      }
      return send(res, 200, {
        answer: CHAT_ANSWER,
        sources: CHAT_SOURCES,
        conversation_id: body.conversation_id || "conv-mock-1",
      });
    }
    if (path === "/api/chat/brief") return send(res, 200, { brief: BRIEF, talking_points: TALKING_POINTS });
    if (path === "/api/monitor/draft-email")
      return send(res, 200, {
        draft:
          "Dear Alan and Lynne,\n\nAhead of our review, I wanted to confirm the pension contribution change and share an updated cashflow projection.\n\nKind regards,",
        subject: "Follow-up: Alan & Lynne Partridge",
      });
    if (path === "/api/ingest/upload")
      return send(res, 200, { id: "uploaded-doc", filename: "sample-client-note.pdf", content_hash: "upload", file_size_bytes: 620, uploaded_at: new Date().toISOString(), processing_error: null });
    if (path === "/api/ingest/transcript")
      return send(res, 201, { id: "transcript-doc", filename: "transcript-abc123.txt", content_hash: "transcript", file_size_bytes: 1200, uploaded_at: new Date().toISOString(), processing_error: null });
    if (path === "/api/ingest/upload-async")
      return send(res, 202, { job_id: "job-async-1", document_id: "job-async-1", status: "PENDING" });
    if (path === "/api/compliance/scan") {
      let body = {};
      try {
        body = rawBody ? JSON.parse(rawBody) : {};
      } catch {
        body = {};
      }
      const text = (body.text || "").toLowerCase();
      const vulnerability_signals = [];
      const consumer_duty_flags = [];
      if (text.includes("cancer") || text.includes("diagnosis"))
        vulnerability_signals.push({ category: "Health", phrase: "diagnosis", excerpt: "…cancer diagnosis…" });
      if (text.includes("redundancy") || text.includes("divorce"))
        vulnerability_signals.push({ category: "Life events", phrase: "redundancy", excerpt: "…redundancy…" });
      if (text.includes("did not understand") || text.includes("unclear"))
        consumer_duty_flags.push({ outcome: "Consumer understanding", phrase: "unclear", excerpt: "…unclear…" });
      return send(res, 200, {
        vulnerability_signals,
        consumer_duty_flags,
        summary: {
          vulnerability_count: vulnerability_signals.length,
          consumer_duty_count: consumer_duty_flags.length,
        },
      });
    }
    if (path === "/api/settings/clear-data") return send(res, 200, { ok: true, message: "All data cleared." });
    if (path === "/api/settings/load-sample-data")
      return send(res, 200, {
        loaded: true,
        message: "Loaded 4 demo clients and 6 alerts.",
        clients: 4,
        alerts: 6,
      });
    return send(res, 404, { detail: "not found" });
  });
});

server.listen(PORT, () => console.log(`Mock backend on http://localhost:${PORT}`));
