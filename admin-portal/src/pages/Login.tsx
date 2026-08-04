import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotSent, setForgotSent] = useState(false);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleForgot(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.forgotPassword(email);
      setForgotSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 mb-8 justify-center">
          <span className="w-2 h-2 rounded-full bg-accent pulse-dot" />
          <span className="font-mono text-sm tracking-widest text-text">GATEWAY</span>
        </div>

        <div className="bg-panel border border-border rounded-lg p-6">
          {forgotMode ? (
            <form onSubmit={handleForgot} className="space-y-4">
              <h1 className="text-text text-base font-medium">Reset password</h1>
              {forgotSent ? (
                <p className="text-sm text-ok">If that email is registered, a reset link has been sent.</p>
              ) : (
                <>
                  <Field label="Email" type="email" value={email} onChange={setEmail} required />
                  {error && <p className="text-sm text-danger">{error}</p>}
                  <button type="submit" disabled={loading} className="btn-primary">
                    {loading ? "Sending..." : "Send reset link"}
                  </button>
                </>
              )}
              <button type="button" onClick={() => { setForgotMode(false); setForgotSent(false); }} className="text-xs text-muted hover:text-text block">
                Back to sign in
              </button>
            </form>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <h1 className="text-text text-base font-medium">Sign in</h1>
              <Field label="Email" type="email" value={email} onChange={setEmail} required />
              <Field label="Password" type="password" value={password} onChange={setPassword} required />
              {error && <p className="text-sm text-danger">{error}</p>}
              <button type="submit" disabled={loading} className="btn-primary">
                {loading ? "Signing in..." : "Sign in"}
              </button>
              <button type="button" onClick={() => setForgotMode(true)} className="text-xs text-muted hover:text-text block">
                Forgot password?
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, type, value, onChange, required }: { label: string; type: string; value: string; onChange: (v: string) => void; required?: boolean }) {
  return (
    <label className="block">
      <span className="text-xs text-muted mb-1 block">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-panelalt border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-accent"
      />
    </label>
  );
}
