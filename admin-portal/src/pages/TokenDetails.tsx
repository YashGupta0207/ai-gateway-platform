import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, DevToken, RequestLog, TokenUsage } from "../api/client";

export default function TokenDetails() {
  const { id = "" } = useParams();
  const [token, setToken] = useState<DevToken | null>(null);
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Promise.all([api.getToken(id, revealed), api.tokenRequests(id), api.tokenUsage(id)]).then(([t, r, u]) => { setToken(t); setLogs(r); setUsage(u); }).catch((e) => setError(e.message)); }, [id, revealed]);
  if (error) return <p className="text-danger text-sm">{error}</p>;
  if (!token) return <p className="text-muted text-sm">loading...</p>;
  const key = token.temporary_api_key || `********${token.token_prefix.slice(-4)}`;
  const stats = [["Today's requests", usage?.today.requests ?? 0], ["Today's tokens", usage?.today.total_tokens ?? 0], ["Monthly requests", usage?.month.requests ?? 0], ["Monthly tokens", usage?.month.total_tokens ?? 0], ["Lifetime requests", token.total_requests], ["Lifetime tokens", token.total_tokens], ["Average latency", `${token.average_latency_ms.toFixed(0)}ms`], ["Last used", token.last_used_at ? new Date(token.last_used_at).toLocaleString() : "never"]];
  return <div className="space-y-6">
    <div><Link to="/tokens" className="text-xs text-accent">← Developer tokens</Link><h1 className="text-lg font-medium text-text mt-2">{token.label}</h1></div>
    <div className="card p-5 space-y-3"><div className="flex gap-3 items-center"><code className="flex-1 text-sm text-accent break-all">{key}</code><button className="btn-secondary text-xs" onClick={() => setRevealed(!revealed)}>{revealed ? "Hide" : "Reveal"}</button><button className="btn-secondary text-xs" onClick={() => token.temporary_api_key && navigator.clipboard.writeText(token.temporary_api_key)}>Copy</button></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs text-muted"><p>Provider <span className="text-text block">{token.provider_name}</span></p><p>Status <span className="text-text block">{token.status}</span></p><p>Expires <span className="text-text block">{token.expires_at ? new Date(token.expires_at).toLocaleDateString() : "Never"}</span></p><p>Last IP <span className="text-text block">{token.last_client_ip || "—"}</span></p></div></div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">{stats.map(([label, value]) => <div key={label as string} className="card p-4"><p className="text-xs text-muted">{label}</p><p className="font-mono text-lg text-text">{value}</p></div>)}</div>
    <div className="card p-5 overflow-auto"><h2 className="text-sm font-medium text-text mb-3">Recent request history</h2><table className="w-full text-xs"><thead><tr className="text-left text-muted"><th>Time</th><th>Endpoint</th><th>Status</th><th>Latency</th><th>Tokens</th><th>IP</th><th>Streaming</th></tr></thead><tbody>{logs.map((row) => <tr key={row.id} className="border-t border-border/50"><td className="py-2">{new Date(row.created_at).toLocaleString()}</td><td>{row.endpoint}</td><td>{row.status_code ?? "—"}</td><td>{row.latency_ms ?? "—"}ms</td><td>{row.total_tokens}</td><td>{row.ip_address || "—"}</td><td>{row.is_streaming ? "yes" : "no"}</td></tr>)}{!logs.length && <tr><td colSpan={7} className="py-4 text-muted">No requests logged yet.</td></tr>}</tbody></table></div>
  </div>;
}
