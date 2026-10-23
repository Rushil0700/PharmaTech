import { useState } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { Field, Loading, Modal, Notice, Pager, useDebounced, useForm, useLoad } from "../components/ui";

function SupplierForm({ supplier, onClose, onSaved }) {
  const { values, bind } = useForm(supplier || { name: "", contact_person: "", phone: "", email: "", gstin: "", address: "" });
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault();
    try {
      supplier ? await patch(`/suppliers/${supplier.id}/`, values) : await post("/suppliers/", values);
      onSaved();
    } catch (err) { setError(err.message); }
  };
  return (
    <Modal title={supplier ? `Edit ${supplier.name}` : "Add supplier"} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" form="sup-form">{supplier ? "Save changes" : "Add supplier"}</button></>}>
      <form id="sup-form" onSubmit={save} className="stack">
        <Notice>{error}</Notice>
        <div className="form-grid">
          <Field label="Business name" full><input className="input" {...bind("name")} required /></Field>
          <Field label="Contact person"><input className="input" {...bind("contact_person")} /></Field>
          <Field label="Phone"><input className="input" {...bind("phone")} /></Field>
          <Field label="Email"><input className="input" type="email" {...bind("email")} /></Field>
          <Field label="GSTIN"><input className="input" maxLength={15} {...bind("gstin")} /></Field>
          <Field label="Address" full><textarea className="input" {...bind("address")} /></Field>
        </div>
      </form>
    </Modal>
  );
}

export default function Suppliers() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(null);
  const [message, setMessage] = useState("");
  const q = useDebounced(search);
  const list = useLoad(() => get("/suppliers/", { search: q, page }), [q, page]);

  const remove = async (s) => {
    if (!confirm(`Delete ${s.name}?`)) return;
    try { await del(`/suppliers/${s.id}/`); list.reload(); setMessage(`${s.name} deleted.`); }
    catch { setMessage(`${s.name} has batches or orders on record, so it can't be deleted.`); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Suppliers</h1><p>Distributors you buy stock from.</p></div>
        {can("suppliers") && <button className="btn primary" onClick={() => setEditing("new")}>Add supplier</button>}
      </div>
      <Notice kind="info">{message}</Notice>
      <section className="panel" style={{ marginTop: message ? 12 : 0 }}>
        <div className="toolbar"><input className="input search" placeholder="Search suppliers" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></div>
        {!list.data ? <Loading /> : list.data.results.length === 0 ? <div className="empty">No suppliers yet. Add the distributors you buy from.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Supplier</th><th>Contact</th><th>GSTIN</th>{can("suppliers") && <th />}</tr></thead>
              <tbody>
                {list.data.results.map((s) => (
                  <tr key={s.id}>
                    <td><strong>{s.name}</strong><span className="sub">{s.address}</span></td>
                    <td>{s.contact_person}<span className="sub">{[s.phone, s.email].filter(Boolean).join(", ")}</span></td>
                    <td>{s.gstin || "—"}</td>
                    {can("suppliers") && <td className="num"><div className="row" style={{ justifyContent: "flex-end" }}>
                      <button className="btn small" onClick={() => setEditing(s)}>Edit</button>
                      <button className="btn small danger" onClick={() => remove(s)}>Delete</button>
                    </div></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager data={list.data} page={page} setPage={setPage} />
      </section>
      {editing && <SupplierForm supplier={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} />}
    </>
  );
}
