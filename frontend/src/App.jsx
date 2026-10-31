import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { clearSession, currentUser, getToken } from "./api";
import AuthPage from "./pages/AuthPage.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Transactions from "./pages/Transactions.jsx";
import UploadPage from "./pages/UploadPage.jsx";

function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = currentUser();
  const links = [
    ["/dashboard", "Dashboard"],
    ["/upload", "Upload"],
    ["/transactions", "Review"],
  ];

  return (
    <div className="app-shell">
      <aside>
        <div className="brand">SpendSense</div>
        <p className="muted">Personal finance tracker</p>
        <nav>
          {links.map(([to, label]) => (
            <button
              key={to}
              className={location.pathname === to ? "nav-link active" : "nav-link"}
              onClick={() => navigate(to)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div>{user?.name}</div>
          <div className="muted">{user?.email}</div>
          <button
            className="ghost"
            onClick={() => {
              clearSession();
              navigate("/login");
            }}
          >
            Log out
          </button>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}

function Private({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      <Route path="/dashboard" element={<Private><Dashboard /></Private>} />
      <Route path="/upload" element={<Private><UploadPage /></Private>} />
      <Route path="/transactions" element={<Private><Transactions /></Private>} />
      <Route path="*" element={<Navigate to={getToken() ? "/dashboard" : "/login"} replace />} />
    </Routes>
  );
}
