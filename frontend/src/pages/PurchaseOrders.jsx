import { useEffect, useState } from "react";
import { get, getAll, post } from "../api";
import { useAuth } from "../auth";
import { Field, Loading, Modal, Notice, Pager, useLoad } from "../components/ui";
import { addDaysISO, date, inr, todayISO } from "../format";

const STATUS = { PENDING: "warning", RECEIVED: "ok", CANCELLED: "neutral" };

function NewOrder({ onClose, onSaved }) {
  const [options, setOptions] = useState(null);
  const [supplier, setSupplier] = useState("");
  const [expected, setExpected] = useState(addDaysISO(todayISO(), 5));
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([{ medicine: "", quantity: 50, unit_cost: "" }]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getAll("/medicines/", { is_active: true }), getAll("/suppliers/"), get("/alerts/")]).then(([m, s, a]) => {
      setOptions({ m, s });
      // Pre-fill with what's running low.
      const low = a.low_stock.slice(0, 5).map((x) => {
        const med = m.find((mm) => mm.id === x.id);
        return { medicine: String(x.id), quantity: Math.max(x.reorder_level * 3, 20), unit_cost: med ? (med.unit_price * 0.65).toFixed(2) : "" };
      });
      if (low.length) setLines(low);
    });
  }, []);

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, j) => {
    if (j !== i) return l;
    const next = { ...l, [k]: v };
    if (k === "medicine" && !l.unit_cost) {
      const med = options.m.find((m) => String(m.id) === v);
      if (med) next.unit_cost = (med.unit_price * 0.65).toFixed(2);
    }
    return next;
  }));
  const total = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0);

  const save = async (e) => {
    e.preventDefault();
    try {
      await post("/purchase-orders/", {
        supplier: Number(supplier), expected_date: expected || null, notes,
        items: lines.filter((l) => l.medicine).map((l) => ({ medicine: Number(l.medicine), quantity: Number(l.quantity), unit_cost: l.unit_cost })),
      });
      onSaved();
    } catch (err) { setError(err.message); }
  };

  return (
    <Modal title="New purchase order" wide onClose={onClose}
      footer={<><span className="muted">Order value {inr(total)}</span><span className="spacer" /><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" form="po-form">Place order</button></>}>
      {!options ? <Loading /> : (
        <form id="po-form" className="stack" onSubmit={save}>
          <Notice>{error}</Notice>
          <div className="form-grid">
            <Field label="Supplier"><select className="input" value={supplier} onChange={(e) => setSupplier(e.target.value)} required>
              <option value="">Choose a supplier</option>{options.s.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select></Field>
            <Field label="Expected delivery"><input className="input" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} /></Field>
          </div>
          <p className="muted small">Medicines below their reorder level are filled in for you.</p>
          <table>
            <thead><tr><th>Medicine</th><th className="num">Quantity</th><th className="num">Cost per unit (₹)</th><th /></tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i}>
                  <td><select className="input" value={l.medicine} onChange={(e) => setLine(i, "medicine", e.target.value)} required>
                    <option value="">Choose a medicine</option>{options.m.map((m) => <option key={m.id} value={m.id}>{m.name} {m.strength} ({m.brand}) · {m.stock} in stock</option>)}
                  </select></td>
                  <td style={{ width: 110 }}><input className="input" type="number" min="1" value={l.quantity} onChange={(e) => setLine(i, "quantity", e.target.value)} required /></td>
                  <td style={{ width: 150 }}><input className="input" type="number" min="0" step="0.01" value={l.unit_cost} onChange={(e) => setLine(i, "unit_cost", e.target.value)} required /></td>
                  <td><button type="button" className="btn small ghost" disabled={lines.length === 1} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div><button type="button" className="btn small" onClick={() => setLines((ls) => [...ls, { medicine: "", quantity: 50, unit_cost: "" }])}>Add another medicine</button></div>
          <Field label="Notes" full><textarea className="input" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        </form>
      )}
    </Modal>
  );
}

function Receive({ order, onClose, onSaved }) {
  const [rows, setRows] = useState(order.items.map((i) => ({
    item: i.id, batch_number: "", mfg_date: addDaysISO(todayISO(), -30), expiry_date: addDaysISO(todayISO(), 730),
  })));
  const [error, setError] = useState("");
  const set = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async (e) => {
    e.preventDefault();
    try { await post(`/purchase-orders/${order.id}/receive/`, { batches: rows }); onSaved(); } catch (err) { setError(err.message); }
  };
  return (
    <Modal title={`Receive ${order.po_number}`} wide onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" form="recv-form">Add to stock</button></>}>
      <form id="recv-form" className="stack" onSubmit={save}>
        <p className="muted small">Copy the batch number and dates from each box. Each line becomes a stock batch.</p>
        <Notice>{error}</Notice>
        <table>
          <thead><tr><th>Medicine</th><th className="num">Qty</th><th>Batch number</th><th>Manufactured</th><th>Expires</th></tr></thead>
          <tbody>
            {order.items.map((it, i) => (
              <tr key={it.id}>
                <td>{it.medicine_name}</td><td className="num">{it.quantity}</td>
                <td><input className="input" value={rows[i].batch_number} onChange={(e) => set(i, "batch_number", e.target.value)} required /></td>
                <td><input className="input" type="date" max={todayISO()} value={rows[i].mfg_date} onChange={(e) => set(i, "mfg_date", e.target.value)} required /></td>
                <td><input className="input" type="date" min={todayISO()} value={rows[i].expiry_date} onChange={(e) => set(i, "expiry_date", e.target.value)} required /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </form>
    </Modal>
  );
}

export default function PurchaseOrders() {
  const { can } = useAuth();
  const [status, setStatus] = useState("PENDING");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [receiving, setReceiving] = useState(null);
  const [message, setMessage] = useState("");
  const list = useLoad(() => get("/purchase-orders/", { status, page }), [status, page]);

  const cancel = async (po) => {
    if (!confirm(`Cancel ${po.po_number}?`)) return;
    try { await post(`/purchase-orders/${po.id}/cancel/`); list.reload(); } catch (err) { setMessage(err.message); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Purchase orders</h1><p>Order from suppliers, then receive the delivery to add it to stock.</p></div>
        {can("orders") && <button className="btn primary" onClick={() => setCreating(true)}>New purchase order</button>}
      </div>
      <Notice kind="info">{message}</Notice>
      <section className="panel" style={{ marginTop: message ? 12 : 0 }}>
        <div className="toolbar"><div className="tabs">
          {[["PENDING", "Waiting for delivery"], ["RECEIVED", "Received"], ["CANCELLED", "Cancelled"], ["", "All"]].map(([v, l]) => (
            <button key={v} className={`tab${status === v ? " active" : ""}`} onClick={() => { setStatus(v); setPage(1); }}>{l}</button>
          ))}
        </div></div>
        {!list.data ? <Loading /> : list.data.results.length === 0 ? <div className="empty">No orders here.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Order</th><th>Supplier</th><th>Medicines</th><th className="num">Value</th><th>Status</th>{can("orders") && <th />}</tr></thead>
              <tbody>
                {list.data.results.map((po) => (
                  <tr key={po.id}>
                    <td><strong>{po.po_number}</strong><span className="sub">Ordered {date(po.order_date)}</span></td>
                    <td>{po.supplier_name}</td>
                    <td>{po.items.map((i) => `${i.medicine_name} × ${i.quantity}`).join(", ")}</td>
                    <td className="num">{inr(po.total_cost)}</td>
                    <td><span className={`badge ${STATUS[po.status]}`}>{po.status === "PENDING" ? `Due ${date(po.expected_date)}` : po.status === "RECEIVED" ? `Received ${date(po.received_date)}` : "Cancelled"}</span></td>
                    {can("orders") && <td className="num">{po.status === "PENDING" && <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button className="btn small primary" onClick={() => setReceiving(po)}>Receive</button>
                      <button className="btn small ghost" onClick={() => cancel(po)}>Cancel</button>
                    </div>}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager data={list.data} page={page} setPage={setPage} />
      </section>
      {creating && <NewOrder onClose={() => setCreating(false)} onSaved={() => { setCreating(false); setStatus("PENDING"); list.reload(); setMessage("Purchase order placed."); }} />}
      {receiving && <Receive order={receiving} onClose={() => setReceiving(null)} onSaved={() => { setReceiving(null); list.reload(); setMessage(`${receiving.po_number} received and added to stock.`); }} />}
    </>
  );
}
