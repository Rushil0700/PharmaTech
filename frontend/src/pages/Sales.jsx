import { useState } from "react";
import { del, get } from "../api";
import { useAuth } from "../auth";
import Invoice from "../components/Invoice";
import { Loading, Notice, Pager, useDebounced, useLoad } from "../components/ui";
import { dateTime, inr } from "../format";

export default function Sales() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [payment, setPayment] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(null);
  const [message, setMessage] = useState("");
  const q = useDebounced(search);
  const list = useLoad(() => get("/sales/", { search: q, date_from: from, date_to: to, payment_method: payment, page }), [q, from, to, payment, page]);

  const view = async (id) => setOpen(await get(`/sales/${id}/`));
  const cancel = async () => {
    if (!confirm(`Cancel bill ${open.invoice_number}? Its medicines go back into stock.`)) return;
    try {
      await del(`/sales/${open.id}/`);
      setMessage(`Cancelled ${open.invoice_number}; stock restored.`);
      setOpen(null);
      list.reload();
    } catch (err) { setMessage(err.message); setOpen(null); }
  };
  const reset = (fn) => (e) => { fn(e.target.value); setPage(1); };
  const recent = open && Date.now() - new Date(open.created_at).getTime() < 24 * 3600 * 1000;

  return (
    <>
      <div className="page-head"><div><h1>Sales history</h1><p>Every bill, newest first. Open one to reprint or cancel it.</p></div></div>
      <Notice kind="info">{message}</Notice>
      <section className="panel" style={{ marginTop: message ? 12 : 0 }}>
        <div className="toolbar">
          <input className="input search" placeholder="Bill number, customer, phone or doctor" value={search} onChange={reset(setSearch)} />
          <label className="row small">From <input className="input" type="date" value={from} onChange={reset(setFrom)} /></label>
          <label className="row small">To <input className="input" type="date" value={to} onChange={reset(setTo)} /></label>
          <select className="input" value={payment} onChange={reset(setPayment)}>
            <option value="">Any payment</option><option value="UPI">UPI</option><option value="CASH">Cash</option><option value="CARD">Card</option>
          </select>
        </div>
        {!list.data ? <Loading /> : list.data.results.length === 0 ? <div className="empty">No bills in this range.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Bill</th><th>When</th><th>Customer</th><th>Payment</th><th className="num">Items</th><th className="num">Total</th></tr></thead>
              <tbody>
                {list.data.results.map((s) => (
                  <tr key={s.id} onClick={() => view(s.id)} style={{ cursor: "pointer" }}>
                    <td><button className="btn ghost small" style={{ padding: 0 }} onClick={(e) => { e.stopPropagation(); view(s.id); }}>{s.invoice_number}</button></td>
                    <td>{dateTime(s.created_at)}</td>
                    <td>{s.customer_name || <span className="muted">Walk-in</span>}{s.doctor_name && <span className="sub">{s.doctor_name}</span>}</td>
                    <td>{s.payment_method}</td>
                    <td className="num">{s.item_count}</td>
                    <td className="num"><strong>{inr(s.total_amount)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager data={list.data} page={page} setPage={setPage} />
      </section>
      {open && <Invoice sale={open} onClose={() => setOpen(null)}
        actions={can("billing") && recent && <button className="btn danger" onClick={cancel}>Cancel bill</button>} />}
    </>
  );
}
