import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, CreatedToken, DevToken, Provider } from "../api/client";

export default function Tokens() {
  const [tokens, setTokens] = useState<DevToken[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [revealed, setRevealed] = useState<CreatedToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewingToken, setViewingToken] = useState<{ token: DevToken, apiKey: string } | null>(null);

  function refresh() {
    api.listTokens().then(setTokens).catch((e) => setError(e.message));
    api.listProviders().then(setProviders).catch(() => { });
  }
  useEffect(refresh, []);

  async function toggle(t: DevToken) {
    try {
      if (t.status === "active") await api.disableToken(t.id);
      else await api.enableToken(t.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update token");
    }
  }

  async function regenerate(t: DevToken) {
    if (!confirm(`Regenerate the token for "${t.label}"? The old token will stop working immediately.`)) return;
    try {
      const created = await api.regenerateToken(t.id);
      setRevealed(created);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to regenerate token");
    }
  }

  async function remove(t: DevToken) {
    if (!confirm(`Delete token "${t.label}"? This cannot be undone.`)) return;
    try {
      await api.deleteToken(t.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete token");
    }
  }

  async function handleView(t: DevToken) {
    try {
      const full = await api.getToken(t.id, true);
      setViewingToken({ token: t, apiKey: full.temporary_api_key || "" });
    } catch (e) { setError(e instanceof Error ? e.message : "Could not reveal token"); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium text-text">Developer tokens</h1>
          <p className="text-sm text-muted">Developers authenticate with these — never with real provider credentials.</p>
        </div>
        {!showForm && (
          <button onClick={() => setShowForm(true)} className="btn-primary w-auto px-4">Generate token</button>
        )}
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {revealed && (
        <div className="card p-5 border-accent/50">
          <p className="text-xs text-warn mb-2">This token is shown once. Copy it now — it can't be retrieved later.</p>
          <div className="flex items-center gap-3">
            <code className="flex-1 bg-panelalt px-3 py-2 rounded text-sm text-accent font-mono break-all">{revealed.raw_token}</code>
            <button
              onClick={() => navigator.clipboard.writeText(revealed.raw_token)}
              className="btn-secondary text-xs px-3 py-2"
            >
              Copy
            </button>
          </div>
          <button onClick={() => setRevealed(null)} className="text-xs text-muted hover:text-text mt-3">Done</button>
        </div>
      )}

      {showForm && (
        <TokenForm
          providers={providers}
          onCreated={(created) => { setShowForm(false); setRevealed(created); refresh(); }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[1250px] text-sm">
          <thead>
            <tr className="text-left text-muted text-xs border-b border-border">
              <th className="px-5 py-3 font-normal">Label</th>
              <th className="px-5 py-3 font-normal">Token</th>
              <th className="px-5 py-3 font-normal">Providers</th>
              <th className="px-5 py-3 font-normal">Status</th>
              <th className="px-5 py-3 font-normal">Requests</th>
              <th className="px-5 py-3 font-normal">Prompt</th>
              <th className="px-5 py-3 font-normal">Completion</th>
              <th className="px-5 py-3 font-normal">Tokens</th>
              <th className="px-5 py-3 font-normal">Avg. time</th>
              <th className="px-5 py-3 font-normal">Expires</th>
              <th className="px-5 py-3 font-normal">Last used</th>
              <th className="px-5 py-3 font-normal">Actions</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id} className="border-b border-border/50">
                <td className="px-5 py-3 text-text"><Link className="hover:text-accent" to={`/tokens/${t.id}`}>{t.label}</Link></td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.token_prefix}…</td>
                <td className="px-5 py-3 text-text">{t.provider_names.join(", ")}</td>
                <td className="px-5 py-3">
                  <span className={t.status === "active" ? "badge-ok" : "badge-warn"}>{t.status}</span>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.total_requests.toLocaleString()}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.prompt_tokens.toLocaleString()}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.completion_tokens.toLocaleString()}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.total_tokens.toLocaleString()}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.average_latency_ms ? `${(t.average_latency_ms / 1000).toFixed(2)}s` : "—"}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.expires_at ? new Date(t.expires_at).toLocaleDateString() : "—"}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "never"}</td>
                <td className="px-5 py-3">
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => handleView(t)} className="text-xs text-muted hover:text-text">View</button>
                    <button onClick={() => toggle(t)} className="text-xs text-muted hover:text-text">
                      {t.status === "active" ? "Disable" : "Enable"}
                    </button>
                    <button onClick={() => regenerate(t)} className="text-xs text-muted hover:text-accent">Regenerate</button>
                    <button onClick={() => remove(t)} className="text-xs text-muted hover:text-danger">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
            {tokens.length === 0 && (
              <tr><td colSpan={7} className="px-5 py-6 text-muted text-xs">No tokens generated yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {viewingToken && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-panel border border-border rounded-lg shadow-xl w-full max-w-md overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-border">
              <h2 className="text-lg font-medium text-text">Token Details</h2>
              <button onClick={() => setViewingToken(null)} className="text-muted hover:text-text">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-xs text-muted mb-1">Generated API Key</label>
                <div className="bg-panelalt border border-border rounded px-3 py-2 text-sm text-accent font-mono break-all">
                  {viewingToken.apiKey}
                </div>
              </div>
              <div>
                <label className="block text-xs text-muted mb-1">Backend URL</label>
                <div className="bg-panelalt border border-border rounded px-3 py-2 text-sm text-accent font-mono break-all">
                  https://ai-gateway-platform-cex4.onrender.com/
                </div>
              </div>
            </div>
            <div className="p-4 border-t border-border flex justify-end">
              <button
                onClick={() => {
                  const textToCopy = `API Key: ${viewingToken.apiKey}\nBackend URL: https://ai-gateway-platform-cex4.onrender.com/`;
                  navigator.clipboard.writeText(textToCopy);
                }}
                className="btn-primary px-4 py-2 text-sm"
              >
                Copy All
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TokenForm({ providers, onCreated, onCancel }: {
  providers: Provider[]; onCreated: (t: CreatedToken) => void; onCancel: () => void;
}) {
  const [label, setLabel] = useState("");
  const [providerIds, setProviderIds] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [limits, setLimits] = useState<Record<string, string>>({});

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const created = await api.createToken({
        label, provider_ids: providerIds, notes: notes || null,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        daily_request_limit: limits.daily_request_limit ? Number(limits.daily_request_limit) : null,
        monthly_request_limit: limits.monthly_request_limit ? Number(limits.monthly_request_limit) : null,
        daily_token_limit: limits.daily_token_limit ? Number(limits.daily_token_limit) : null,
        monthly_token_limit: limits.monthly_token_limit ? Number(limits.monthly_token_limit) : null,
      });
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create token");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card p-6 space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className="text-xs text-muted mb-1 block">Label</span>
          <input required value={label} onChange={(e) => setLabel(e.target.value)}
            className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent" />
        </label>
        <div className="block">
          <span className="text-xs text-muted mb-1 block">Allowed Providers</span>
          <div className="bg-panelalt border border-border rounded p-3 max-h-40 overflow-y-auto space-y-2">
            {providers.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-sm text-text cursor-pointer">
                <input
                  type="checkbox"
                  checked={providerIds.includes(p.id)}
                  onChange={(e) => {
                    if (e.target.checked) setProviderIds([...providerIds, p.id]);
                    else setProviderIds(providerIds.filter(id => id !== p.id));
                  }}
                  className="rounded border-border bg-panel text-accent focus:ring-accent"
                />
                {p.name}
              </label>
            ))}
            {providers.length === 0 && <span className="text-xs text-muted">No providers available</span>}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {[['daily_request_limit', 'Daily request limit'], ['monthly_request_limit', 'Monthly request limit'], ['daily_token_limit', 'Daily token limit'], ['monthly_token_limit', 'Monthly token limit']].map(([key, title]) => (
          <label key={key} className="block"><span className="text-xs text-muted mb-1 block">{title} (optional)</span>
            <input type="number" min="1" value={limits[key] || ""} onChange={(e) => setLimits({ ...limits, [key]: e.target.value })} className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text" />
          </label>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className="text-xs text-muted mb-1 block">Expires (optional)</span>
          <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)}
            className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent" />
        </label>
        <label className="block">
          <span className="text-xs text-muted mb-1 block">Notes (optional)</span>
          <input value={notes} onChange={(e) => setNotes(e.target.value)}
            className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent" />
        </label>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex gap-3">
        <button type="submit" disabled={saving} className="btn-primary w-auto px-5">{saving ? "Generating..." : "Generate token"}</button>
        <button type="button" onClick={onCancel} className="btn-secondary">Cancel</button>
      </div>
    </form>
  );
}
