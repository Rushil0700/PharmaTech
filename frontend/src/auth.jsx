import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { get, hasTokens, post, setLogoutHandler, setTokens } from "./api";

const AuthContext = createContext(null);

// What each role may change (the API enforces the same rules).
const WRITE = {
  Admin: ["medicines", "billing", "stock", "suppliers", "orders", "users"],
  Pharmacist: ["medicines", "billing"],
  "Store Staff": ["stock", "suppliers", "orders"],
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => { setTokens(null); setUser(null); }, []);
  useEffect(() => setLogoutHandler(logout), [logout]);

  useEffect(() => {
    if (!hasTokens()) { setReady(true); return; }
    get("/auth/me/").then(setUser).catch(() => setTokens(null)).finally(() => setReady(true));
  }, []);

  const login = async (username, password) => {
    const tokens = await post("/auth/login/", { username, password });
    setTokens(tokens);
    const me = await get("/auth/me/");
    if (!me.role) { setTokens(null); throw new Error("This account has no role yet. Ask an admin to assign one."); }
    setUser(me);
  };

  const can = (area) => Boolean(user && WRITE[user.role]?.includes(area));
  return <AuthContext.Provider value={{ user, ready, login, logout, can }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
