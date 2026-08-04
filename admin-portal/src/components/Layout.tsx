import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api/client";

const NAV = [
  { to: "/", label: "Dashboard", jack: "01" },
  { to: "/providers", label: "Providers", jack: "02" },
  { to: "/tokens", label: "Tokens", jack: "03" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex bg-base">
      <aside className="w-64 shrink-0 border-r border-border bg-panel flex flex-col">
        <div className="px-5 py-5 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent pulse-dot" />
            <span className="font-mono text-sm tracking-wide text-text">GATEWAY</span>
          </div>
          <p className="text-xs text-muted mt-1 font-mono">control plane</p>
        </div>

        <nav className="flex-1 py-4">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-3 text-sm border-l-2 transition-colors ${
                  isActive
                    ? "border-accent text-text bg-panelalt"
                    : "border-transparent text-muted hover:text-text hover:bg-panelalt/50"
                }`
              }
            >
              <span className="font-mono text-[10px] text-muted">{item.jack}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-5 border-t border-border">
          <button
            onClick={() => {
              api.logout();
              navigate("/login");
            }}
            className="w-full text-sm text-muted hover:text-danger transition-colors text-left"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
