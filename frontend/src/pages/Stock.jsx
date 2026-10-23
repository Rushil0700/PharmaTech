import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { get, getAll, post } from "../api";
import { useAuth } from "../auth";
import { Field, Loading, Modal, Notice, Pager, StatusBadge, useDebounced, useForm, useLoad } from "../components/ui";
import { addDaysISO, date, daysLabel, expiryStatus, inr, todayISO } from "../format";

const FILTERS = [["", "All batches"], ["critical", "Under 30 days"], ["warning", "30 to 90 days"], ["expired", "Expired"], ["ok", "Good"]];

function BatchForm({ onClose, onSaved }) {
  const [options, setOptions] = useState(null);
  const { values, bind } = useForm({
    medicine: "", supplier: "", batch_number: "", quantity_received: "", cost_price: "",
    mfg_date: addDaysISO(todayISO(), -30), expiry_date: addDaysISO(todayISO(), 730), received_date: todayISO(),
  });
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([getAll("/medicines/", { is_active: true }), getAll("/suppliers/")]).then(([m, s]) => setOptions({ m, s })); }, []);

  const save = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await post("/batches/", { ...values, medicine: Number(values.medicine), supplier: Number(values.supplier), quantity_received: Number(values.quantity_received) });
      onSaved();
    } catch (err) { setError(err.message); }
  };

  return (
    <Modal title="Receive a batch" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" form="batch-form">Add to stock</button></>}>
      {!options ? <Loading /> : (
        <form id="batch-form" onSubmit={save} className="stack">
          <p className="muted small">For deliveries without a purchase order. Orders you raised in PharmaTrack are received from the Purchase orders page.</p>
          <Notice>{error}</Notice>
          <div className="form-grid">
            <Field label="Medicine" full>
              <select className="input" {...bind("medicine")} required>
                <option value="">Choose a medicine</option>
                {options.m.map((m) => <option key={m.id} value={m.id}>{m.name} {m.strength} ({m.brand})</option>)}
              </select>
            </Field>
            <Field label="Supplier">
              <select className="input" {...bind("supplier")} required>
                <option value="">Choose a supplier</option>
                {options.s.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Batch number"><input className="input" {...bind("batch_number")} required /></Field>
            <Field label="Quantity received"><input className="input" type="number" min="1" {...bind("quantity_received")} required /></Field>
            <Field label="Cost per unit (₹)"><input className="input" type="number" min="0" step="0.01" {...bind("cost_price")} required /></Field>
            <Field label="Manufactured on"><input className="input" type="date" max={todayISO()} {...bind("mfg_date")} required /></Field>
            <Field label="Expires on"><input className="input" type="date" {...bind("expiry_date")} required /></Field>
            <Field label="Received on"><input className="input" type="date" max={todayISO()} {...bind("received_date")} required /></Field>
          </div>
        </form>
      )}
    </Modal>
  );
}

export default function Stock() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const [search, setSearch] = useState("");
  const [inStock, setInStock] = useState(true);
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState("");
  const q = useDebounced(search);
  const list = useLoad(() => get("/batches/", { status, search: q, in_stock: inStock ? 1 : "", page, ordering: "expiry_date" }), [status, q, inStock, page]);

  const writeOff = async (b) => {
    if (!confirm(`Write off ${b.quantity_available} units of ${b.medicine_name} (batch ${b.batch_number})? This records them as a loss.`)) return;
    try {
      await post(`/batches/${b.id}/write_off/`, { quantity: b.quantity_available });
      setMessage(`Wrote off batch ${b.batch_number}.`);
      list.reload();
    } catch (err) { setMessage(err.message); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Stock & expiry</h1><p>Every batch on the shelf, soonest expiry first. Billing always sells from the top of this list.</p></div>
        {can("stock") && <button className="btn primary" onClick={() => setAdding(true)}>Receive a batch</button>}
      </div>
      <Notice kind="info">{message}</Notice>
      <section className="panel" style={{ marginTop: message ? 12 : 0 }}>
        <div className="toolbar">
          <div className="tabs" role="tablist">
            {FILTERS.map(([value, label]) => (
              <button key={value} role="tab" aria-selected={status === value} className={`tab${status === value ? " active" : ""}`}
                onClick={() => { setParams(value ? { status: value } : {}); setPage(1); }}>{label}</button>
            ))}
          </div>
          <input className="input search" placeholder="Search medicine or batch number" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
          <label className="check"><input type="checkbox" checked={inStock} onChange={(e) => { setInStock(e.target.checked); setPage(1); }} /> Hide empty batches</label>
        </div>
        {!list.data ? <Loading /> : list.data.results.length === 0 ? <div className="empty">No batches in this view.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Medicine</th><th>Batch</th><th>Supplier</th><th className="num">Units left</th><th className="num">Value at cost</th><th>Expiry</th><th>Status</th>{can("stock") && <th />}</tr></thead>
              <tbody>
                {list.data.results.map((b) => {
                  const st = expiryStatus(b.days_to_expiry);
                  return (
                    <tr key={b.id} className={`edge-${st}`}>
                      <td><strong>{b.medicine_name}</strong></td>
                      <td>{b.batch_number}<span className="sub">Received {date(b.received_date)}</span></td>
                      <td>{b.supplier_name}</td>
                      <td className="num">{b.quantity_available}<span className="sub">of {b.quantity_received}</span></td>
                      <td className="num">{inr(b.stock_value)}</td>
                      <td>{date(b.expiry_date)}<span className="sub">{daysLabel(b.days_to_expiry)}</span></td>
                      <td><StatusBadge status={st} /></td>
                      {can("stock") && <td className="num">{st === "expired" && b.quantity_available > 0 && <button className="btn small danger" onClick={() => writeOff(b)}>Write off</button>}</td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <Pager data={list.data} page={page} setPage={setPage} />
      </section>
      {adding && <BatchForm onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setMessage("Batch added to stock."); list.reload(); }} />}
    </>
  );
}
