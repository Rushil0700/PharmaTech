import { useMemo, useState } from "react";
import { get, post } from "../api";
import Invoice from "../components/Invoice";
import { Field, Notice, useDebounced, useLoad } from "../components/ui";
import { date, inr } from "../format";

export default function Billing() {
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 200);
  const results = useLoad(() => get("/medicines/", { search: q, is_active: true, ordering: "-stock" }), [q]);
  const [cart, setCart] = useState([]);
  const [customer, setCustomer] = useState({ customer_name: "", customer_phone: "", doctor_name: "", payment_method: "UPI", discount: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  const add = (m) => {
    setError("");
    setCart((c) => {
      const found = c.find((l) => l.medicine.id === m.id);
      if (found) return c.map((l) => (l.medicine.id === m.id ? { ...l, quantity: Math.min(l.quantity + 1, m.stock) } : l));
      return [...c, { medicine: m, quantity: 1 }];
    });
  };
  const setQty = (id, qty) => setCart((c) => c.map((l) => (l.medicine.id === id ? { ...l, quantity: qty } : l)));
  const remove = (id) => setCart((c) => c.filter((l) => l.medicine.id !== id));

  const subtotal = useMemo(() => cart.reduce((s, l) => s + Number(l.medicine.unit_price) * (Number(l.quantity) || 0), 0), [cart]);
  const discount = Math.min(Number(customer.discount) || 0, subtotal);
  const needsRx = cart.some((l) => l.medicine.requires_prescription);
  const set = (k) => (e) => setCustomer((c) => ({ ...c, [k]: e.target.value }));

  const checkout = async () => {
    setBusy(true);
    setError("");
    try {
      const sale = await post("/sales/", {
        ...customer, discount: discount.toFixed(2),
        items: cart.map((l) => ({ medicine: l.medicine.id, quantity: Number(l.quantity) })),
      });
      setDone(sale);
      setCart([]);
      setCustomer({ customer_name: "", customer_phone: "", doctor_name: "", payment_method: "UPI", discount: "" });
      results.reload();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>New bill</h1><p>Stock is taken from the batch that expires first, automatically.</p></div>
      </div>
      <div className="counter">
        <section className="panel">
          <div className="toolbar">
            <input className="input search" autoFocus placeholder="Type a medicine, brand or ingredient" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search medicines" />
          </div>
          <div className="results">
            {results.data?.results.length === 0 && <div className="empty">Nothing matches “{search}”.</div>}
            {results.data?.results.map((m) => {
              const inCart = cart.find((l) => l.medicine.id === m.id)?.quantity || 0;
              const out = m.stock - inCart <= 0;
              return (
                <div key={m.id} className={`result${m.stock === 0 ? " out" : ""}`}>
                  <div style={{ flex: 1 }}>
                    <div className="name">{m.name} {m.strength} {m.requires_prescription && <span className="badge rx">Rx</span>}</div>
                    <div className="muted small">{m.brand} · {m.stock} in stock{m.nearest_expiry && `, next batch expires ${date(m.nearest_expiry)}`}</div>
                  </div>
                  <strong>{inr(m.unit_price)}</strong>
                  <button className="btn small primary" disabled={out} onClick={() => add(m)}>{m.stock === 0 ? "Out of stock" : inCart ? "Add one more" : "Add"}</button>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><h2>Bill</h2>{cart.length > 0 && <button className="btn small ghost" onClick={() => setCart([])}>Clear</button>}</div>
          <div className="panel-body stack">
            {cart.length === 0 ? <p className="muted">Add medicines from the list to start a bill.</p> : (
              <div>
                {cart.map((l) => (
                  <div className="cart-line" key={l.medicine.id}>
                    <div><strong>{l.medicine.name} {l.medicine.strength}</strong><div className="muted small">{inr(l.medicine.unit_price)} each</div></div>
                    <input className="input" type="number" min="1" max={l.medicine.stock} value={l.quantity}
                      onChange={(e) => setQty(l.medicine.id, e.target.value)} aria-label={`Quantity of ${l.medicine.name}`} />
                    <button className="btn small ghost" onClick={() => remove(l.medicine.id)} aria-label={`Remove ${l.medicine.name}`}>Remove</button>
                  </div>
                ))}
              </div>
            )}
            <div className="form-grid">
              <Field label="Customer name"><input className="input" value={customer.customer_name} onChange={set("customer_name")} /></Field>
              <Field label="Phone"><input className="input" value={customer.customer_phone} onChange={set("customer_phone")} /></Field>
              <Field label={needsRx ? "Prescribing doctor (required)" : "Prescribing doctor"} full>
                <input className="input" value={customer.doctor_name} onChange={set("doctor_name")} required={needsRx} />
              </Field>
              <Field label="Payment">
                <select className="input" value={customer.payment_method} onChange={set("payment_method")}>
                  <option value="UPI">UPI</option><option value="CASH">Cash</option><option value="CARD">Card</option>
                </select>
              </Field>
              <Field label="Discount (₹)"><input className="input" type="number" min="0" step="0.01" value={customer.discount} onChange={set("discount")} /></Field>
            </div>
            <div className="totals">
              <span className="muted">Subtotal</span><span>{inr(subtotal)}</span>
              {discount > 0 && <><span className="muted">Discount</span><span>− {inr(discount)}</span></>}
              <span className="grand">Total</span><span className="grand">{inr(subtotal - discount)}</span>
            </div>
            <Notice>{error}</Notice>
            <button className="btn primary" disabled={!cart.length || busy || (needsRx && !customer.doctor_name.trim())} onClick={checkout}>
              {busy ? "Creating bill…" : `Create bill for ${inr(subtotal - discount)}`}
            </button>
          </div>
        </section>
      </div>
      {done && <Invoice sale={done} onClose={() => setDone(null)} />}
    </>
  );
}
