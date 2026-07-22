// k6 load baseline for KritiFin (run against STAGING, never production).
//
//   k6 run load/k6-baseline.js \
//     -e API_URL=https://<staging-function-url>.lambda-url.eu-west-2.on.aws \
//     -e TOKEN="$SUPABASE_ACCESS_TOKEN"
//
// Targets (from the production-readiness RFC):
//   p95 pulse < 800ms at 5 orgs x 250 clients; 5xx rate < 0.5%.
// The chat scenario exercises the full RAG path and is rate-limit aware
// (30/min per org) — keep its arrival rate below that.

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const API = __ENV.API_URL || "http://localhost:8000";
const TOKEN = __ENV.TOKEN || "";
const TODAY = new Date().toISOString().slice(0, 10);

const errorRate = new Rate("errors");
const pulseTrend = new Trend("pulse_ms", true);
const chatTrend = new Trend("chat_ms", true);

const HEADERS = {
  "Content-Type": "application/json",
  ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
};

export const options = {
  scenarios: {
    dashboard: {
      // An adviser's morning: pulse + clients + digest reads.
      executor: "ramping-vus",
      exec: "dashboardJourney",
      startVUs: 1,
      stages: [
        { duration: "1m", target: 10 },
        { duration: "3m", target: 10 },
        { duration: "1m", target: 0 },
      ],
    },
    copilot: {
      // Low, realistic chat volume (respects the 30/min per-org limit).
      executor: "constant-arrival-rate",
      exec: "copilotQuery",
      rate: 20,
      timeUnit: "1m",
      duration: "5m",
      preAllocatedVUs: 5,
    },
  },
  thresholds: {
    errors: ["rate<0.005"],
    pulse_ms: ["p(95)<800"],
    http_req_failed: ["rate<0.01"],
  },
};

export function dashboardJourney() {
  const pulse = http.get(
    `${API}/api/monitor/pulse?simulated_date=${TODAY}`,
    { headers: HEADERS, tags: { name: "pulse" } }
  );
  pulseTrend.add(pulse.timings.duration);
  errorRate.add(pulse.status >= 500);
  check(pulse, { "pulse 200": (r) => r.status === 200 });

  const clients = http.get(`${API}/api/monitor/clients`, {
    headers: HEADERS,
    tags: { name: "clients" },
  });
  errorRate.add(clients.status >= 500);
  check(clients, { "clients 200": (r) => r.status === 200 });

  const alerts = http.get(`${API}/api/monitor/alerts?days=90`, {
    headers: HEADERS,
    tags: { name: "alerts" },
  });
  errorRate.add(alerts.status >= 500);

  sleep(Math.random() * 3 + 1);
}

export function copilotQuery() {
  const res = http.post(
    `${API}/api/chat/`,
    JSON.stringify({ query: "Which clients have ISA allowance remaining this year?" }),
    { headers: HEADERS, tags: { name: "chat" }, timeout: "60s" }
  );
  chatTrend.add(res.timings.duration);
  errorRate.add(res.status >= 500);
  check(res, { "chat 200/429": (r) => r.status === 200 || r.status === 429 });
}
