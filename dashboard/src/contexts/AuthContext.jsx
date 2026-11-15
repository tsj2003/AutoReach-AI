import { createContext, useContext, useEffect, useState } from "react";
import { api, clearTokens, getAccessToken, getRefreshToken, setTokens } from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getAccessToken()) {
      setLoading(false);
      return;
    }
    api
      .get("/api/auth/me")
      .then(setUser)
      .catch(() => clearTokens())
      .finally(() => setLoading(false));
  }, []);

  async function login(email, password) {
    const data = await api.post("/api/auth/login", { email, password });
    setTokens(data);
    const me = await api.get("/api/auth/me");
    setUser(me);
    return me;
  }

  async function signup(email, password, full_name, company_name) {
    const data = await api.post("/api/auth/signup", {
      email,
      password,
      full_name,
      company_name,
    });
    setTokens(data);
    const me = await api.get("/api/auth/me");
    setUser(me);
    return me;
  }

  async function googleLogin(credential) {
    const data = await api.post("/api/auth/google", { credential });
    setTokens(data);
    const me = await api.get("/api/auth/me");
    setUser(me);
    return me;
  }

  async function refreshUser() {
    // The plan lives in the JWT, so after an upgrade we mint a fresh token
    // (refresh re-reads the tenant's current plan) before reloading the user.
    try {
      const refresh = getRefreshToken();
      if (refresh) {
        const data = await api.post("/api/auth/refresh", { refresh_token: refresh });
        setTokens(data);
      }
    } catch (_) {
      // fall through — we'll still try /me with the existing token
    }
    const me = await api.get("/api/auth/me");
    setUser(me);
    return me;
  }

  function logout() {
    clearTokens();
    setUser(null);
    window.location.href = "/app/login";
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, googleLogin, refreshUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
