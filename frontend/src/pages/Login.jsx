import { useState } from "react";
import { useAuth } from "../auth";
import { Notice } from "../components/ui";

const DEMO = [["admin", "admin123", "Admin"], ["pharmacist", "pharma123", "Pharmacist"], ["staff", "staff123", "Store staff"]];

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try { await login(username, password); } catch (err) {
      setError(err.status === 401 ? "That username and password don't match an account." : err.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="login">
      <section className="login-art">
        <div>
          <h1>Every strip on the shelf, accounted for.</h1>
          <p>Track medicine stock batch by batch, bill with first-expiry-first-out, and see what expires next before it becomes a loss.</p>
          <div className="strip" aria-hidden="true">
            {Array.from({ length: 8 }, (_, i) => <span key={i} className={i > 4 ? "gone" : ""} />)}
          </div>
        </div>
        <p className="small">PharmaTrack · React, Django, PostgreSQL, Grafana</p>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <h2>Sign in</h2>
          <Notice>{error}</Notice>
          <div className="field"><label>Username<input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus /></label></div>
          <div className="field"><label>Password<input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label></div>
          <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          <div className="demo-logins">
            Demo accounts:{" "}
            {DEMO.map(([u, p, label], i) => (
              <span key={u}>{i > 0 && ", "}<button type="button" onClick={() => { setUsername(u); setPassword(p); }}>{label}</button></span>
            ))}
          </div>
        </form>
      </section>
    </div>
  );
}
