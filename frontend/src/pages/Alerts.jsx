import { Link } from "react-router-dom";
import { get } from "../api";
import { Loading, Notice, StatusBadge, useLoad } from "../components/ui";
import { date, daysLabel, expiryStatus, inr } from "../format";

function BatchTable({ rows, empty }) {
  if (!rows.length) return <div className="empty">{empty}</div>;
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Medicine</th><th>Batch</th><th>Supplier</th><th className="num">Units</th><th className="num">Value</th><th>Expiry</th><th>Status</th></tr></thead>
      <tbody>{rows.map((b) => {
        const st = expiryStatus(b.days_to_expiry);
        return (
          <tr key={b.id} className={`edge-${st}`}>
            <td><strong>{b.medicine_name}</strong></td><td>{b.batch_number}</td><td>{b.supplier_name}</td>
            <td className="num">{b.quantity_available}</td><td className="num">{inr(b.stock_value)}</td>
            <td>{date(b.expiry_date)}<span className="sub">{daysLabel(b.days_to_expiry)}</span></td><td><StatusBadge status={st} /></td>
          </tr>
        );
      })}</tbody>
    </table></div>
  );
}

export default function Alerts() {
  const { data, error } = useLoad(() => get("/alerts/"));
  if (error) return <Notice>{error.message}</Notice>;
  if (!data) return <Loading />;
  const { counts } = data;
  const lossValue = data.expired.reduce((s, b) => s + Number(b.stock_value), 0);

  return (
    <>
      <div className="page-head">
        <div><h1>Alerts</h1><p>What needs action today. Grafana sends the same alerts by email.</p></div>
        <Link to="/purchase-orders" className="btn primary">Reorder stock</Link>
      </div>
      <div className="figures">
        <div className={`figure${counts.low_stock ? " warn" : ""}`}><div className="value">{counts.low_stock}</div><div className="label">Below reorder level</div></div>
        <div className={`figure${counts.expired ? " bad" : ""}`}><div className="value">{counts.expired}</div><div className="label">Expired batches on shelf</div></div>
        <div className={`figure${counts.expiring_30 ? " bad" : ""}`}><div className="value">{counts.expiring_30}</div><div className="label">Expiring in 30 days</div></div>
        <div className="figure"><div className="value">{counts.expiring_60}</div><div className="label">Expiring in 60 days</div></div>
        <div className="figure"><div className="value">{counts.expiring_90}</div><div className="label">Expiring in 90 days</div></div>
      </div>
      <div className="stack">
        <section className="panel">
          <div className="panel-head"><h2>Running low</h2></div>
          {data.low_stock.length === 0 ? <div className="empty">Every medicine is above its reorder level.</div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Medicine</th><th>Category</th><th className="num">In stock</th><th className="num">Reorder at</th><th className="num">Short by</th></tr></thead>
              <tbody>{data.low_stock.map((m) => (
                <tr key={m.id} className={m.stock === 0 ? "edge-critical" : "edge-warning"}>
                  <td><strong>{m.name}</strong></td><td>{m.category}</td>
                  <td className="num">{m.stock === 0 ? <span className="badge bad">Out of stock</span> : m.stock}</td>
                  <td className="num">{m.reorder_level}</td><td className="num">{m.shortfall}</td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head"><h2>Expired, remove from shelf</h2>{lossValue > 0 && <span className="badge bad">{inr(lossValue)} at cost</span>}</div>
          <BatchTable rows={data.expired} empty="No expired stock on the shelf." />
        </section>
        <section className="panel">
          <div className="panel-head"><h2>Expiring within 90 days</h2><Link to="/stock?status=critical" className="btn small">Open in stock</Link></div>
          <BatchTable rows={data.expiring} empty="Nothing expires in the next 90 days." />
        </section>
      </div>
    </>
  );
}
