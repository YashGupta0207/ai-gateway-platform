import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Provider } from "../api/client";
import ProviderForm from "../components/ProviderForm";

export default function Providers() {
  const navigate = useNavigate();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.listProviders().then(setProviders).catch((e) => setError(e.message));
  }

  useEffect(refresh, []);

  async function toggle(p: Provider) {
    try {
      if (p.status === "enabled") await api.disableProvider(p.id);
      else await api.enableProvider(p.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update provider");
    }
  }

  async function remove(p: Provider) {
    if (!confirm(`Delete provider "${p.name}"? This also removes its credential variables and cannot be undone.`)) return;
    try {
      await api.deleteProvider(p.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete provider");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium text-text">Providers</h1>
          <p className="text-sm text-muted">Data-driven — any provider type, any set of credential variables. Nothing here is hardcoded.</p>
        </div>
        {!showForm && (
          <button onClick={() => setShowForm(true)} className="btn-primary w-auto px-4">Add provider</button>
        )}
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {showForm && (
        <ProviderForm
          onSaved={() => { setShowForm(false); refresh(); }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted text-xs border-b border-border">
              <th className="px-5 py-3 font-normal">Provider Name</th>
              <th className="px-5 py-3 font-normal">Type</th>
              <th className="px-5 py-3 font-normal">Status</th>
              <th className="px-5 py-3 font-normal">Variables</th>
              <th className="px-5 py-3 font-normal">Tokens</th>
              <th className="px-5 py-3 font-normal">Last used</th>
              <th className="px-5 py-3 font-normal">Created</th>
              <th className="px-5 py-3 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id} className="border-b border-border/50 hover:bg-panelalt/40 transition-colors">
                <td className="px-5 py-3">
                  <button onClick={() => navigate(`/providers/${p.id}`)} className="text-text hover:text-accent text-left">
                    {p.name}
                  </button>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{p.provider_type}</td>
                <td className="px-5 py-3">
                  <span className={p.status === "enabled" ? "badge-ok" : "badge-warn"}>{p.status}</span>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-text">{p.credential_count}</td>
                <td className="px-5 py-3 font-mono text-xs text-text">{p.token_count}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{p.last_used_at ? new Date(p.last_used_at).toLocaleString() : "never"}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{new Date(p.created_at).toLocaleDateString()}</td>
                <td className="px-5 py-3">
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => navigate(`/providers/${p.id}`)} className="text-xs text-muted hover:text-accent">View</button>
                    <button onClick={() => toggle(p)} className="text-xs text-muted hover:text-text">
                      {p.status === "enabled" ? "Disable" : "Enable"}
                    </button>
                    <button onClick={() => remove(p)} className="text-xs text-muted hover:text-danger">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
            {providers.length === 0 && !showForm && (
              <tr><td colSpan={8} className="px-5 py-6 text-muted text-xs">No providers configured yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
