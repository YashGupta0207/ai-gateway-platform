const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

function getTokens() {
  return {
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
  };
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

async function refreshAccessToken(): Promise<boolean> {
  const { refresh } = getTokens();
  if (!refresh) return false;
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return true;
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const { access } = getTokens();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (res.status === 401 && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, options, false);
    clearTokens();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `Request failed (${res.status})`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }).then((data) => {
      setTokens(data.access_token, data.refresh_token);
      return data;
    }),

  logout: () => {
    clearTokens();
  },

  forgotPassword: (email: string) =>
    request("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),

  resetPassword: (reset_token: string, new_password: string) =>
    request("/auth/reset-password", { method: "POST", body: JSON.stringify({ reset_token, new_password }) }),

  dashboardSummary: () => request<DashboardSummary>("/dashboard/summary"),

  listProviders: () => request<Provider[]>("/providers"),
  getProvider: (id: string) => request<ProviderDetails>(`/providers/${id}`),
  availableAdapters: () => request<AvailableAdapter[]>("/providers/available-adapters"),
  createProvider: (payload: unknown) => request<Provider>("/providers", { method: "POST", body: JSON.stringify(payload) }),
  updateProvider: (id: string, payload: unknown) => request<Provider>(`/providers/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  enableProvider: (id: string) => request<Provider>(`/providers/${id}/enable`, { method: "POST" }),
  disableProvider: (id: string) => request<Provider>(`/providers/${id}/disable`, { method: "POST" }),
  deleteProvider: (id: string) => request<void>(`/providers/${id}`, { method: "DELETE" }),
  rotateCredentials: (id: string, profileId: string, pairs: { variable_name: string; value: string }[]) =>
    request<Profile>(`/providers/${id}/profiles/${profileId}/rotate-credentials`, { method: "POST", body: JSON.stringify(pairs) }),
  deleteCredentialVariable: (id: string, profileId: string, variableName: string) =>
    request<void>(`/providers/${id}/profiles/${profileId}/credentials/${encodeURIComponent(variableName)}`, { method: "DELETE" }),
  revealCredential: (id: string, profileId: string, variableName: string) =>
    request<{ variable_name: string; value: string }>(`/providers/${id}/profiles/${profileId}/credentials/${encodeURIComponent(variableName)}/reveal`),

  listTokens: () => request<DevToken[]>("/tokens"),
  getToken: (id: string, reveal = false) => request<DevToken>(`/tokens/${id}${reveal ? "?reveal=true" : ""}`),
  tokenRequests: (id: string) => request<RequestLog[]>(`/tokens/${id}/requests`),
  tokenUsage: (id: string) => request<TokenUsage>(`/tokens/${id}/usage`),
  createToken: (payload: unknown) => request<CreatedToken>("/tokens", { method: "POST", body: JSON.stringify(payload) }),
  updateTokenLimits: (id: string, payload: TokenLimits) =>
    request<DevToken>(`/tokens/${id}/limits`, { method: "PATCH", body: JSON.stringify(payload) }),
  disableToken: (id: string) => request<DevToken>(`/tokens/${id}/disable`, { method: "POST" }),
  enableToken: (id: string) => request<DevToken>(`/tokens/${id}/enable`, { method: "POST" }),
  regenerateToken: (id: string) => request<CreatedToken>(`/tokens/${id}/regenerate`, { method: "POST" }),
  deleteToken: (id: string) => request<void>(`/tokens/${id}`, { method: "DELETE" }),

  isAuthenticated: () => !!getTokens().access,
};

export interface DashboardSummary {
  total_providers: number;
  total_tokens: number;
  active_tokens: number;
  disabled_tokens: number;
  requests_last_24h: number;
  expired_tokens: number;
  requests_this_month: number;
  tokens_today: number;
  tokens_this_month: number;
  recent_requests: { endpoint: string; method: string; status_code: number | null; latency_ms: number | null; created_at: string }[];
  provider_status: { id: string; display_name: string; status: string }[];
  top_developers: { name: string; requests: number; total_tokens: number }[];
  top_providers: { name: string; requests: number; total_tokens: number }[];
}

export interface CredentialField {
  name: string;
  label: string;
  field_type: string;
  required: boolean;
  is_mandatory_primary: boolean;
  placeholder: string;
}

export interface AvailableAdapter {
  adapter_key: string;
  display_name: string;
  suggested_variables: CredentialField[];
}

export interface CredentialPair {
  variable_name: string;
  value: string;
}

export interface Provider {
  id: string;
  name: string;
  provider_type: string;
  description: string | null;
  status: "enabled" | "disabled";
  credential_count: number;
  token_count: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Profile {
  id: string;
  name: string;
  is_active: boolean;
  is_default: boolean;
  priority: number;
}

export interface ProfileDetails extends Profile {
  credentials: { variable_name: string; masked_value: string }[];
}

export interface ProviderDetails extends Provider {
  profiles: ProfileDetails[];
  total_requests: number;
  total_tokens_used: number;
}

export interface TokenLimits {
  daily_request_limit?: number | null;
  monthly_request_limit?: number | null;
  daily_token_limit?: number | null;
  monthly_token_limit?: number | null;
}

export interface DevToken {
  id: string;
  label: string;
  token_prefix: string;
  temporary_api_key?: string | null;
  provider_ids: string[];
  provider_names: string[];
  status: "active" | "disabled";
  notes: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
  last_client_ip?: string | null;
  last_user_agent?: string | null;
  daily_request_limit?: number | null;
  monthly_request_limit?: number | null;
  daily_token_limit?: number | null;
  monthly_token_limit?: number | null;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  first_used_at: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  average_latency_ms: number;
  estimated_cost: number;
}

export interface CreatedToken extends Omit<DevToken, "token_prefix"> {
  raw_token: string;
}

export interface RequestLog {
  id: string; created_at: string; endpoint: string; method: string; status_code: number | null;
  latency_ms: number | null; prompt_tokens: number; completion_tokens: number; total_tokens: number;
  ip_address: string | null; user_agent: string | null; is_streaming: boolean;
}

export interface TokenUsage { today: { requests: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }; month: { requests: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }; }
