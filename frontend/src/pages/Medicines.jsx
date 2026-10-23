import { useState } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { Field, Loading, Modal, Notice, Pager, useDebounced, useForm, useLoad } from "../components/ui";
import { date, inr } from "../format";

const FORMS = ["TABLET", "CAPSULE", "SYRUP", "INJECTION", "OINTMENT", "DROPS", "INHALER", "POWDER", "OTHER"];
const title = (s) => s.charAt(0) + s.slice(1).toLowerCase();

function MedicineForm({ medicine, categories, onClose, onSaved }) {
  const { values, bind } = useForm(medicine || {
    name: "", brand: "", strength: "", composition: "", category: categories[0]?.id || "",
    dosage_form: "TABLET", unit_price: "", reorder_level: 20, requires_prescription: false, is_active: true,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = { ...values, category: Number(values.category), reorder_level: Number(values.reorder_level) };
      medicine ? await patch(`/medicines/${medicine.id}/`, body) : await post("/medicines/", body);
      onSaved();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return (
    <Modal title={medicine ? `Edit ${medicine.name}` : "Add medicine"} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" form="med-form" disabled={busy}>{medicine ? "Save changes" : "Add medicine"}</button></>}>
      <form id="med-form" onSubmit={save} className="stack">
        <Notice>{error}</Notice>
        <div className="form-grid">
          <Field label="Generic name"><input className="input" {...bind("name")} required /></Field>
          <Field label="Brand"><input className="input" {...bind("brand")} /></Field>
          <Field label="Strength or pack size"><input className="input" {...bind("strength")} placeholder="500 mg" /></Field>
          <Field label="Category">
            <select className="input" {...bind("category")} required>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Composition" full><input className="input" {...bind("composition")} placeholder="Active ingredients" /></Field>
          <Field label="Form">
            <select className="input" {...bind("dosage_form")}>{FORMS.map((f) => <option key={f} value={f}>{title(f)}</option>)}</select>
          </Field>
          <Field label="Selling price per unit (₹)"><input className="input" type="number" min="0" step="0.01" {...bind("unit_price")} required /></Field>
          <Field label="Reorder level" hint="You'll get a low-stock alert below this quantity."><input className="input" type="number" min="0" {...bind("reorder_level")} required /></Field>
          <div className="field" style={{ justifyContent: "flex-end", gap: 10 }}>
            <label className="check"><input {...bind("requires_prescription", "checkbox")} /> Needs a prescription</label>
            {medicine && <label className="check"><input {...bind("is_active", "checkbox")} /> Available for sale</label>}
          </div>
        </div>
      </form>
    </Modal>
  );
}

export default function Medicines() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(null);
  const [message, setMessage] = useState("");
  const q = useDebounced(search);

  const categories = useLoad(() => get("/categories/"));
  const list = useLoad(() => get("/medicines/", { search: q, category, low_stock: lowOnly ? 1 : "", page }), [q, category, lowOnly, page]);

  const remove = async (m) => {
    if (!confirm(`Remove ${m.name} ${m.strength}?`)) return;
    try {
      const res = await del(`/medicines/${m.id}/`);
      setMessage(res?.detail || `${m.name} removed.`);
      list.reload();
    } catch (err) { setMessage(err.message); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Medicines</h1><p>Your catalogue. Stock counts only include batches that haven't expired.</p></div>
        {can("medicines") && <button className="btn primary" onClick={() => setEditing("new")}>Add medicine</button>}
      </div>
      <Notice kind="info">{message}</Notice>
      <section className="panel" style={{ marginTop: message ? 12 : 0 }}>
        <div className="toolbar">
          <input className="input search" placeholder="Search by name, brand or ingredient" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
          <select className="input" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
            <option value="">All categories</option>
            {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={lowOnly} onChange={(e) => { setLowOnly(e.target.checked); setPage(1); }} /> Low stock only</label>
        </div>
        {list.error && <div className="panel-body"><Notice>{list.error.message}</Notice></div>}
        {!list.data ? <Loading /> : list.data.results.length === 0 ? <div className="empty">No medicines match. Try a different search.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Medicine</th><th>Category</th><th className="num">Price</th><th className="num">In stock</th><th>Next expiry</th>{can("medicines") && <th />}</tr></thead>
              <tbody>
                {list.data.results.map((m) => (
                  <tr key={m.id} className={m.stock === 0 ? "edge-critical" : m.is_low_stock ? "edge-warning" : ""}>
                    <td>
                      <strong>{m.name} {m.strength}</strong> {m.requires_prescription && <span className="badge rx">Rx</span>} {!m.is_active && <span className="badge neutral">Inactive</span>}
                      <span className="sub">{[m.brand, m.dosage_form_display].filter(Boolean).join(", ")}</span>
                    </td>
                    <td>{m.category_name}</td>
                    <td className="num">{inr(m.unit_price)}</td>
                    <td className="num">
                      {m.stock === 0 ? <span className="badge bad">Out of stock</span> : m.is_low_stock ? <span className="badge warning">{m.stock} · low</span> : m.stock}
                    </td>
                    <td>{date(m.nearest_expiry)}</td>
                    {can("medicines") && (
                      <td className="num"><div className="row" style={{ justifyContent: "flex-end" }}>
                        <button className="btn small" onClick={() => setEditing(m)}>Edit</button>
                        <button className="btn small danger" onClick={() => remove(m)}>Remove</button>
                      </div></td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager data={list.data} page={page} setPage={setPage} />
      </section>
      {editing && categories.data && (
        <MedicineForm medicine={editing === "new" ? null : editing} categories={categories.data}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} />
      )}
    </>
  );
}
