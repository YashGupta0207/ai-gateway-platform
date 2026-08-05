import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ProviderDetails as ProviderDetailsType } from "../api/client";
import ProviderForm from "../components/ProviderForm";

export default function ProviderDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [provider, setProvider] = useState<ProviderDetailsType | null>(null);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    if (!id) return;
    api.getProvider(id).then(setProvider).catch((e) => setError(e.message));
  }

  useEffect(refresh, [id]);

  async function reveal(profileId: string, variableName: string) {
    if (!id) return;
    try {
      const result = await api.revealCredential(id, profileId, variableName);
      setRevealed((prev) => ({ ...prev, [`${profileId}-${variableName}`]: result.value }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reveal credential");
    }
  }

  async function remove(profileId: string, variableName: string) {
    if (!id || !confirm(`Delete variable "${variableName}"?`)) return;
    try {
      await api.deleteCredentialVariable(id, profileId, variableName);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete variable");
    }
  }

  if (error) return <p className="text-danger text-sm">{error}</p>;
  if (!provider) return <p className="text-muted text-sm font-mono">loading...</p>;

  if (editing) {
    return (
      <div className="space-y-6">
        <button onClick={() => setEditing(false)} className="text-xs text-muted hover:text-text">&larr; Back to details</button>
        <ProviderForm existing={provider} onSaved={() => { setEditing(false); refresh(); }} onCancel={() => setEditing(false)} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button onClick={() => navigate("/providers")} className="text-xs text-muted hover:text-text">&larr; Back to providers</button>

      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-medium text-text">{provider.name}</h1>
            <span className={provider.status === "enabled" ? "badge-ok" : "badge-warn"}>{provider.status}</span>
          </div>
          <p className="text-sm text-muted font-mono mt-1">{provider.provider_type}</p>
          {provider.description && <p className="text-sm text-muted mt-2 max-w-xl">{provider.description}</p>}
        </div>
        <button onClick={() => setEditing(true)} className="btn-secondary text-xs px-3 py-1.5">Edit</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Developer tokens" value={provider.token_count} />
        <Stat label="Total requests" value={provider.total_requests} />
        <Stat label="Total tokens used" value={provider.total_tokens_used} />
        <Stat label="Last used" value={provider.last_used_at ? new Date(provider.last_used_at).toLocaleString() : "never"} />
      </div>

      <div className="grid grid-cols-2 gap-4 text-xs text-muted">
        <div>Created: <span className="text-text font-mono">{new Date(provider.created_at).toLocaleString()}</span></div>
        <div>Updated: <span className="text-text font-mono">{new Date(provider.updated_at).toLocaleString()}</span></div>
      </div>

      <div className="space-y-6">
        <h2 className="text-base font-medium text-text">Profiles</h2>
        {provider.profiles.map((profile) => (
          <div key={profile.id} className="card overflow-hidden">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h3 className="text-sm font-medium text-text">{profile.name}</h3>
                  {profile.is_default && <span className="badge-ok">Default</span>}
                  {!profile.is_active && <span className="badge-warn">Inactive</span>}
                </div>
                <p className="text-xs text-muted mt-1">Priority: {profile.priority}</p>
              </div>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted text-xs border-b border-border">
                  <th className="px-5 py-3 font-normal">Key</th>
                  <th className="px-5 py-3 font-normal">Value</th>
                  <th className="px-5 py-3 font-normal"></th>
                </tr>
              </thead>
              <tbody>
                {profile.credentials.map((c) => {
                  const revealKey = `${profile.id}-${c.variable_name}`;
                  return (
                    <tr key={c.variable_name} className="border-b border-border/50">
                      <td className="px-5 py-3 font-mono text-text">{c.variable_name}</td>
                      <td className="px-5 py-3 font-mono text-xs text-text break-all">
                        {revealed[revealKey] ?? c.masked_value}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex gap-3 justify-end">
                          {revealed[revealKey] ? <>
                            <button onClick={() => setRevealed((values) => { const next = { ...values }; delete next[revealKey]; return next; })} className="text-xs text-muted hover:text-accent">Hide</button>
                            <button onClick={() => navigator.clipboard.writeText(revealed[revealKey])} className="text-xs text-muted hover:text-accent">Copy</button>
                          </> : <button onClick={() => reveal(profile.id, c.variable_name)} className="text-xs text-muted hover:text-accent">Reveal</button>}
                          <button onClick={() => remove(profile.id, c.variable_name)} className="text-xs text-muted hover:text-danger">Delete</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {profile.credentials.length === 0 && (
                  <tr><td colSpan={3} className="px-5 py-6 text-muted text-xs">No credential variables configured.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        ))}
        {provider.profiles.length === 0 && (
          <div className="card p-6 text-center text-muted text-sm">No profiles configured.</div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className="font-mono text-xl text-text">{value}</p>
    </div>
  );
}
