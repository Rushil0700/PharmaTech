import { useState } from "react";
import { get, patch, post } from "../api";
import { Field, Loading, Modal, Notice, useForm, useLoad } from "../components/ui";
import { dateTime } from "../format";

const ROLES = { Admin: "Everything, including users", Pharmacist: "Billing and the medicine catalogue", "Store Staff": "Stock, suppliers and purchase orders" };

function NewUser({ onClose, onSaved }) {
  const { values, bind } = useForm({ username: "", first_name: "", last_name: "", email: "", password: "", role: "Pharmacist" });
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault();
    try { await post("/users/", values); onSaved(); } catch (err) { setError(err.message); }
  };
  return (
    <Modal title="Add user" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" form="user-form">Add user</button></>}>
      <form id="user-form" className="stack" onSubmit={save}>
        <Notice>{error}</Notice>
        <div className="form-grid">
          <Field label="Username"><input className="input" {...bind("username")} required /></Field>
          <Field label="Temporary password" hint="At least 6 characters."><input className="input" type="password" minLength={6} {...bind("password")} required /></Field>
          <Field label="First name"><input className="input" {...bind("first_name")} /></Field>
          <Field label="Last name"><input className="input" {...bind("last_name")} /></Field>
          <Field label="Email" full><input className="input" type="email" {...bind("email")} /></Field>
          <Field label="Role" full hint={ROLES[values.role]}>
            <select className="input" {...bind("role")}>{Object.keys(ROLES).map((r) => <option key={r}>{r}</option>)}</select>
          </Field>
        </div>
      </form>
    </Modal>
  );
}

export default function Users() {
  const list = useLoad(() => get("/users/"));
  const [adding, setAdding] = useState(false);
  const toggle = async (u) => { await patch(`/users/${u.id}/`, { is_active: !u.is_active }); list.reload(); };
  const rows = list.data?.results || [];
  return (
    <>
      <div className="page-head">
        <div><h1>Users</h1><p>Who can sign in, and what each person can change.</p></div>
        <button className="btn primary" onClick={() => setAdding(true)}>Add user</button>
      </div>
      <section className="panel">
        {!list.data ? <Loading /> : (
          <table>
            <thead><tr><th>User</th><th>Role</th><th>Last sign-in</th><th /></tr></thead>
            <tbody>{rows.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.username}</strong><span className="sub">{[u.first_name, u.last_name].filter(Boolean).join(" ") || u.email}</span></td>
                <td>{u.role || <span className="badge neutral">No role</span>}</td>
                <td>{dateTime(u.last_login)}</td>
                <td className="num"><button className={`btn small${u.is_active ? " danger" : ""}`} onClick={() => toggle(u)}>{u.is_active ? "Disable" : "Enable"}</button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>
      {adding && <NewUser onClose={() => setAdding(false)} onSaved={() => { setAdding(false); list.reload(); }} />}
    </>
  );
}
