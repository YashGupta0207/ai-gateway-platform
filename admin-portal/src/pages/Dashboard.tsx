import { useEffect, useState } from "react";
import { api, DashboardSummary } from "../api/client";

export default function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboardSummary().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="text-danger text-sm">{error}</p>;
  if (!data) return <p className="text-muted text-sm font-mono">loading...</p>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-lg font-medium text-text">Dashboard</h1>
        <p className="text-sm text-muted">Live view of the gateway.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Providers" value={data.total_providers} />
        <Stat label="Tokens" value={data.total_tokens} />
        <Stat label="Active tokens" value={data.active_tokens} accent="ok" />
        <Stat label="Disabled tokens" value={data.disabled_tokens} accent="warn" />
        <Stat label="Expired tokens" value={data.expired_tokens} accent="warn" />
        <Stat label="Requests this month" value={data.requests_this_month} />
        <Stat label="Tokens today" value={data.tokens_today} />
        <Stat label="Tokens this month" value={data.tokens_this_month} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-5">
          <h2 className="text-sm font-medium text-text mb-4">Provider status</h2>
          <div className="space-y-2">
            {data.provider_status.length === 0 && <p className="text-xs text-muted">No providers configured yet.</p>}
            {data.provider_status.map((p) => (
              <div key={p.id} className="flex items-center justify-between text-sm">
                <span className="text-text">{p.display_name}</span>
                <span className={p.status === "enabled" ? "badge-ok" : "badge-warn"}>{p.status}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-medium text-text mb-1">Requests, last 24h</h2>
          <p className="font-mono text-3xl text-accent">{data.requests_last_24h}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Rankings title="Top developers" rows={data.top_developers} />
        <Rankings title="Top providers" rows={data.top_providers} />
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-medium text-text mb-4">Recent activity</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted text-xs border-b border-border">
              <th className="pb-2 font-normal">Endpoint</th>
              <th className="pb-2 font-normal">Method</th>
              <th className="pb-2 font-normal">Status</th>
              <th className="pb-2 font-normal">Latency</th>
              <th className="pb-2 font-normal">Time</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_requests.length === 0 && (
              <tr><td colSpan={5} className="py-4 text-muted text-xs">No requests logged yet.</td></tr>
            )}
            {data.recent_requests.map((r, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="py-2 font-mono text-xs text-text">{r.endpoint}</td>
                <td className="py-2 font-mono text-xs text-muted">{r.method}</td>
                <td className="py-2 font-mono text-xs">
                  <span className={r.status_code && r.status_code < 400 ? "text-ok" : "text-danger"}>
                    {r.status_code ?? "—"}
                  </span>
                </td>
                <td className="py-2 font-mono text-xs text-muted">{r.latency_ms ? `${r.latency_ms}ms` : "—"}</td>
                <td className="py-2 font-mono text-xs text-muted">{new Date(r.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Rankings({ title, rows }: { title: string; rows: { name: string; requests: number; total_tokens: number }[] }) {
  return <div className="card p-5"><h2 className="text-sm font-medium text-text mb-3">{title}</h2>{rows.length ? rows.map((row) => <div key={row.name} className="flex justify-between py-2 border-b border-border/50 text-xs"><span className="text-text">{row.name}</span><span className="font-mono text-muted">{row.total_tokens.toLocaleString()} tokens · {row.requests} requests</span></div>) : <p className="text-xs text-muted">No usage recorded yet.</p>}</div>;
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: "ok" | "warn" }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className={`font-mono text-2xl ${accent === "ok" ? "text-ok" : accent === "warn" ? "text-warn" : "text-text"}`}>
        {value}
      </p>
    </div>
  );
}
