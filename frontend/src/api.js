const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function getToken() {
  return localStorage.getItem("spendsense_token");
}

export function setSession(token, user) {
  localStorage.setItem("spendsense_token", token);
  localStorage.setItem("spendsense_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("spendsense_token");
  localStorage.removeItem("spendsense_user");
}

export function currentUser() {
  const raw = localStorage.getItem("spendsense_user");
  return raw ? JSON.parse(raw) : null;
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (response.status === 401) {
    clearSession();
  }
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.headers.get("content-type")?.includes("application/json")) {
    return response.json();
  }
  return response;
}

export const api = {
  register: (payload) => request("/api/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload) => request("/api/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  dashboard: () => request("/api/reports/dashboard"),
  transactions: (params = {}) => {
    const query = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v))).toString();
    return request(`/api/transactions${query ? `?${query}` : ""}`);
  },
  categories: () => request("/api/transactions/categories"),
  classifierStatus: () => request("/api/transactions/classifier-status"),
  reclassify: () => request("/api/transactions/reclassify", { method: "POST" }),
  updateCategory: (id, category) =>
    request(`/api/transactions/${id}`, { method: "PATCH", body: JSON.stringify({ category }) }),
  uploadPdf: (file, sourceType) => {
    const body = new FormData();
    body.append("file", file);
    body.append("source_type", sourceType);
    return request("/api/uploads/pdf", { method: "POST", body });
  },
  exportUrl: `${API}/api/reports/export.xlsx`,
};
