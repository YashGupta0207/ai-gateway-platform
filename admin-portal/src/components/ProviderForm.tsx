import { useState, useEffect } from "react";
import { Provider, ProviderDetails, api, AvailableAdapter, ProfileDetails } from "../api/client";

interface CredentialRow {
  key: string;
  variable_name: string;
  value: string;
}

interface ProfileFormState {
  key: string;
  id?: string;
  name: string;
  is_active: boolean;
  is_default: boolean;
  priority: number;
  credentials: CredentialRow[];
}

let rowSeq = 0;
const newRow = (variable_name = "", value = ""): CredentialRow => ({ key: `row-${++rowSeq}`, variable_name, value });

let profileSeq = 0;
const newProfile = (name = "Default"): ProfileFormState => ({
  key: `profile-${++profileSeq}`,
  name,
  is_active: true,
  is_default: false,
  priority: 0,
  credentials: [newRow()],
});

export default function ProviderForm({
  existing, onSaved, onCancel,
}: {
  existing?: ProviderDetails;
  onSaved: (p: Provider) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(existing?.name || "");
  const [providerType, setProviderType] = useState(existing?.provider_type || "");
  const [description, setDescription] = useState(existing?.description || "");

  const [profiles, setProfiles] = useState<ProfileFormState[]>(
    existing && existing.profiles && existing.profiles.length > 0
      ? existing.profiles.map((p) => ({
        key: `profile-${++profileSeq}`,
        id: p.id,
        name: p.name,
        is_active: p.is_active,
        is_default: p.is_default,
        priority: p.priority,
        credentials: p.credentials.length > 0 ? p.credentials.map((c) => newRow(c.variable_name, "")) : [newRow()],
      }))
      : [newProfile()]
  );

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [adapters, setAdapters] = useState<AvailableAdapter[]>([]);

  useEffect(() => {
    api.availableAdapters().then(setAdapters).catch(console.error);
  }, []);

  function applySuggestion(adapterKey: string) {
    const adapter = adapters.find((a) => a.adapter_key === adapterKey);
    if (!adapter) return;

    setProfiles((prev) => prev.map((p, idx) => {
      if (idx !== 0) return p; // Only apply to the first profile
      const currentKeys = p.credentials.map((r) => r.variable_name);
      const newRows = adapter.suggested_variables
        .filter((v) => !currentKeys.includes(v.name))
        .map((v) => newRow(v.name, ""));

      if (newRows.length > 0) {
        // Remove empty rows if we are adding suggestions
        const filteredCreds = p.credentials.filter(c => c.variable_name.trim() !== "");
        return { ...p, credentials: [...filteredCreds, ...newRows] };
      }
      return p;
    }));
  }

  function addProfile() {
    setProfiles((prev) => [...prev, newProfile(`Profile ${prev.length + 1}`)]);
  }

  function removeProfile(key: string) {
    setProfiles((prev) => prev.filter((p) => p.key !== key));
  }

  function updateProfile(key: string, patch: Partial<ProfileFormState>) {
    setProfiles((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  }

  function addRow(profileKey: string) {
    setProfiles((prev) => prev.map((p) => {
      if (p.key === profileKey) {
        return { ...p, credentials: [...p.credentials, newRow()] };
      }
      return p;
    }));
  }

  function removeRow(profileKey: string, rowKey: string) {
    setProfiles((prev) => prev.map((p) => {
      if (p.key === profileKey) {
        return { ...p, credentials: p.credentials.filter((r) => r.key !== rowKey) };
      }
      return p;
    }));
  }

  function updateRow(profileKey: string, rowKey: string, patch: Partial<CredentialRow>) {
    setProfiles((prev) => prev.map((p) => {
      if (p.key === profileKey) {
        return {
          ...p,
          credentials: p.credentials.map((r) => (r.key === rowKey ? { ...r, ...patch } : r)),
        };
      }
      return p;
    }));
  }

  function validate(): string | null {
    if (!name.trim()) return "Provider name is required.";
    if (!providerType.trim()) return "Provider type is required.";
    if (profiles.length === 0) return "At least one profile is required.";

    for (const p of profiles) {
      if (!p.name.trim()) return "Profile name is required.";
      const names = p.credentials.map((r) => r.variable_name.trim().toLocaleLowerCase()).filter(Boolean);
      if (new Set(names).size !== names.length) return `Variable names must be unique within profile '${p.name}'.`;

      for (const r of p.credentials) {
        if (r.variable_name.trim() && !r.value.trim() && !p.id) {
          return `A value is required for '${r.variable_name}' in profile '${p.name}'.`;
        }
      }
    }
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSaving(true);

    try {
      const payloadProfiles = profiles.map(p => ({
        name: p.name,
        is_active: p.is_active,
        is_default: p.is_default,
        priority: p.priority,
        credentials: p.credentials
          .filter((r) => r.variable_name.trim() && r.value.trim())
          .map((r) => ({ variable_name: r.variable_name.trim(), value: r.value }))
      }));

      let saved: Provider;
      if (existing) {
        saved = await api.updateProvider(existing.id, {
          name, provider_type: providerType, description: description || null,
          profiles: payloadProfiles
        });
      } else {
        saved = await api.createProvider({
          name, provider_type: providerType, description: description || null,
          profiles: payloadProfiles
        });
      }
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save provider");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card p-6 space-y-5">
      <div>
        <h2 className="text-sm font-medium text-text mb-1">{existing ? "Edit provider" : "Configure a provider"}</h2>
        <p className="text-xs text-muted">
          Configure the provider and its deployment profiles.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className="text-xs text-muted mb-1 block">Provider Name</span>
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Azure OpenAI"
            className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent" />
        </label>
        <label className="block">
          <span className="text-xs text-muted mb-1 block">Provider Type</span>
          <input
            required list="adapter-suggestions" value={providerType}
            onChange={(e) => setProviderType(e.target.value)}
            onBlur={(e) => { if (adapters.some((a) => a.adapter_key === e.target.value)) applySuggestion(e.target.value); }}
            placeholder="e.g. Azure, Gemini, Deepgram, Custom REST API, CosmosDB..."
            className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <datalist id="adapter-suggestions">
            {adapters.map((a) => <option key={a.adapter_key} value={a.adapter_key}>{a.display_name}</option>)}
          </datalist>
          <span className="text-[11px] text-muted mt-1 block">Free text — any value works. Recognized types prefill suggested variables below.</span>
        </label>
      </div>

      <label className="block">
        <span className="text-xs text-muted mb-1 block">Description (optional)</span>
        <input value={description} onChange={(e) => setDescription(e.target.value)}
          className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent" />
      </label>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-text">Profiles</h3>
          <button type="button" onClick={addProfile} className="btn-secondary text-xs px-3 py-1.5">
            + Add Profile
          </button>
        </div>

        {profiles.map((profile, pIdx) => (
          <div key={profile.key} className="border border-border rounded p-4 space-y-4 bg-panelalt/30">
            <div className="flex items-start justify-between gap-4">
              <label className="block flex-1">
                <span className="text-xs text-muted mb-1 block">Profile Name</span>
                <input required value={profile.name} onChange={(e) => updateProfile(profile.key, { name: e.target.value })} placeholder="e.g. Azure-EastUS"
                  className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent" />
              </label>
              <div className="flex items-center gap-4 mt-6">
                <label className="flex items-center gap-2 text-xs text-text cursor-pointer">
                  <input type="checkbox" checked={profile.is_default} onChange={(e) => {
                    // If setting this to default, unset others
                    if (e.target.checked) {
                      setProfiles(prev => prev.map(p => p.key === profile.key ? { ...p, is_default: true } : { ...p, is_default: false }));
                    } else {
                      updateProfile(profile.key, { is_default: false });
                    }
                  }} className="rounded border-border bg-panelalt text-accent focus:ring-accent" />
                  Default
                </label>
                <label className="flex items-center gap-2 text-xs text-text cursor-pointer">
                  <input type="checkbox" checked={profile.is_active} onChange={(e) => updateProfile(profile.key, { is_active: e.target.checked })}
                    className="rounded border-border bg-panelalt text-accent focus:ring-accent" />
                  Active
                </label>
                {profiles.length > 1 && (
                  <button type="button" onClick={() => removeProfile(profile.key)} className="text-xs text-danger hover:text-danger/80">
                    Remove Profile
                  </button>
                )}
              </div>
            </div>

            <div>
              <span className="text-xs text-muted mb-2 block">Key / Value pairs</span>
              <div className="space-y-2">
                {profile.credentials.map((row) => (
                  <div key={row.key} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
                    <div>
                      <input
                        value={row.variable_name}
                        onChange={(e) => updateRow(profile.key, row.key, { variable_name: e.target.value })}
                        placeholder="Key (e.g. Azure_API_Key)"
                        className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                    <div>
                      <input
                        type="password"
                        value={row.value}
                        onChange={(e) => updateRow(profile.key, row.key, { value: e.target.value })}
                        placeholder={profile.id ? "•••• (unchanged)" : "Value"}
                        className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => removeRow(profile.key, row.key)}
                      className="mt-1 text-xs text-muted hover:text-danger px-2 py-1"
                      title="Delete variable"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
              <button type="button" onClick={() => addRow(profile.key)} className="text-xs text-accent hover:text-accent/80 mt-2">
                + Add Row
              </button>
            </div>
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="flex gap-3 pt-2">
        <button type="submit" disabled={saving} className="btn-primary w-auto px-5">
          {saving ? "Saving..." : existing ? "Save changes" : "Save provider"}
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary">Cancel</button>
      </div>
    </form>
  );
}
