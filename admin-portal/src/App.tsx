import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Providers from "./pages/Providers";
import ProviderDetails from "./pages/ProviderDetails";
import Tokens from "./pages/Tokens";
import TokenDetails from "./pages/TokenDetails";

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!api.isAuthenticated()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/providers" element={<Providers />} />
                <Route path="/providers/:id" element={<ProviderDetails />} />
                <Route path="/tokens" element={<Tokens />} />
                <Route path="/tokens/:id" element={<TokenDetails />} />
              </Routes>
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
