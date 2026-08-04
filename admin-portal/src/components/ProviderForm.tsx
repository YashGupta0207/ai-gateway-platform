import { useState, useEffect } from "react";
import { Provider, ProviderDetails, api, AvailableAdapter } from "../api/client";

interface Row {
  key: string;   // stable React key, independent of the (editable) variable_name
  variable_name: string;
  value: string;
}

let rowSeq = 0;
const newRow = (variable_name = "", value = ""): Row => ({ key: `row-${++rowSeq}`, variable_name, value });

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
  const [rows, setRows] = useState<Row[]>(
    existing ? existing.credentials.map((c) => newRow(c.variable_name, "")) : [newRow()]
  );
  const [removedNames, setRemovedNames] = useState<string[]>([]);
  const originalNames = existing ? existing.credentials.map((c) => c.variable_name) : [];
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [adapters, setAdapters] = useState<AvailableAdapter[]>([]);

  useEffect(() => {
    api.availableAdapters().then(setAdapters).catch(console.error);
  }, []);

  function applySuggestion(adapterKey: string) {
    const adapter = adapters.find((a) => a.adapter_key === adapterKey);
    if (!adapter) return;
    const currentKeys = rows.map((r) => r.variable_name);
    const newRows = adapter.suggested_variables
      .filter((v) => !currentKeys.includes(v.name))
      .map((v) => newRow(v.name, ""));
    if (newRows.length > 0) {
      setRows((prev) => [...prev, ...newRows]);
    }
  }

  function updateRow(key: string, patch: Partial<Row>) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((prev) => [...prev, newRow()]);
  }

  function removeRow(key: string) {
    setRows((prev) => {
      if (prev.length <= 1) return prev;
      const target = prev.find((r) => r.key === key);
      if (target && originalNames.includes(target.variable_name)) {
        setRemovedNames((names) => [...names, target.variable_name]);
      }
      return prev.filter((r) => r.key !== key);
    });
  }

  function validate(): string | null {
    if (!name.trim()) return "Provider name is required.";
    if (!providerType.trim()) return "Provider type is required.";
    if (rows.some((r) => !r.variable_name.trim())) return "Every key is required.";
    const names = rows.map((r) => r.variable_name.trim().toLocaleLowerCase());
    if (new Set(names).size !== names.length) return "Variable names must be unique.";
    for (const r of rows) {
      const original = originalNames.includes(r.variable_name);
      if (!r.value.trim() && !(existing && original)) {
        return `A value is required for '${r.variable_name}'.`;
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
      let saved: Provider;
      if (existing) {
        // Metadata only — credentials are handled separately below so that
        // rows left blank (meaning "keep the current value") never get
        // wiped out by a full-replace.
        saved = await api.updateProvider(existing.id, {
          name, provider_type: providerType, description: description || null,
        });

        const changedPairs = rows
          .filter((r) => r.variable_name.trim() && r.value.trim())
          .map((r) => ({ variable_name: r.variable_name.trim(), value: r.value }));
        if (changedPairs.length) {
          saved = await api.rotateCredentials(existing.id, changedPairs);
        }
        for (const name of removedNames) {
          await api.deleteCredentialVariable(existing.id, name);
        }
      } else {
        const credentials = rows
          .filter((r) => r.variable_name.trim() && r.value.trim())
          .map((r) => ({ variable_name: r.variable_name.trim(), value: r.value }));
        saved = await api.createProvider({ name, provider_type: providerType, description: description || null, credentials });
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
          Add as many variable/value pairs as this provider needs — nothing here is hardcoded.
          {existing && " Leave a row's value blank to keep its current (encrypted) value unchanged."}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className="text-xs text-muted mb-1 block">Provider Name</span>
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Azure OpenAI — Production"
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

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted">Key / Value pairs</span>
        </div>
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.key} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
              <div>
                <span className="text-[10px] text-muted block mb-1">Key</span>
                <input
                  value={row.variable_name}
                  onChange={(e) => updateRow(row.key, { variable_name: e.target.value })}
                  placeholder="e.g. Azure_OpenAI"
                  className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div>
                <span className="text-[10px] text-muted block mb-1">Value</span>
                <input
                  type="password"
                  value={row.value}
                  onChange={(e) => updateRow(row.key, { value: e.target.value })}
                  placeholder={existing ? "•••• (unchanged)" : "value"}
                  className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <button
                type="button"
                onClick={() => removeRow(row.key)}
                className="mt-[22px] text-xs text-muted hover:text-danger px-2 py-2"
                title="Delete variable"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
        <button type="button" onClick={addRow} className="btn-secondary text-xs px-3 py-1.5 mt-3">
          + Add Row
        </button>
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
