import { Link } from "react-router-dom";
import { get } from "../api";
import GrafanaEmbed from "../components/GrafanaEmbed";
import { Loading, Notice, useLoad } from "../components/ui";
import { inr0 } from "../format";

export default function Dashboard() {
  const { data: d, error } = useLoad(() => get("/dashboard/"));
  if (error) return <Notice>{error.message}</Notice>;
  if (!d) return <Loading />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</p>
        </div>
      </div>

      <div className="figures">
        <div className="figure"><div className="value">{inr0(d.revenue_today)}</div><div className="label">Sales today, {d.bills_today} bills</div></div>
        <div className="figure"><div className="value">{inr0(d.stock_value)}</div><div className="label">Sellable stock at cost</div></div>
        <Link to="/alerts" className={`figure${d.low_stock ? " warn" : ""}`}><div className="value">{d.low_stock}</div><div className="label">Medicines below reorder level</div></Link>
        <Link to="/stock?status=critical" className={`figure${d.expiring_30 ? " bad" : ""}`}><div className="value">{d.expiring_30}</div><div className="label">Batches expiring in 30 days</div></Link>
        <Link to="/stock?status=expired" className={`figure${Number(d.expired_value) ? " bad" : ""}`}><div className="value">{inr0(d.expired_value)}</div><div className="label">Expired stock to write off</div></Link>
      </div>

      <div className="stack">
        <GrafanaEmbed />
      </div>
    </>
  );
}
