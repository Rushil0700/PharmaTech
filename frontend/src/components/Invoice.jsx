import { Modal } from "./ui";
import { date, dateTime, inr } from "../format";

export default function Invoice({ sale, onClose, actions }) {
  return (
    <Modal title={`Bill ${sale.invoice_number}`} onClose={onClose} wide
      footer={<>{actions}<button className="btn primary" onClick={() => window.print()}>Print bill</button></>}>
      <div className="invoice">
        <div className="invoice-head">
          <div>
            <h2>PharmaTrack Pharmacy</h2>
            <p className="muted small">Retail drug licence: GJ-AHD-20B-000000 · GSTIN 24AAAAA0000A1Z5</p>
          </div>
          <div style={{ textAlign: "right" }}>
            <strong>{sale.invoice_number}</strong>
            <p className="small">{dateTime(sale.created_at)}</p>
            <p className="small">Paid by {sale.payment_method}</p>
          </div>
        </div>
        <p className="small" style={{ marginBottom: 10 }}>
          {sale.customer_name ? <>Customer: <strong>{sale.customer_name}</strong>{sale.customer_phone && `, ${sale.customer_phone}`}</> : "Walk-in customer"}
          {sale.doctor_name && <> · Prescribed by {sale.doctor_name}</>}
        </p>
        <table>
          <thead><tr><th>Medicine</th><th>Batch</th><th>Expiry</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
          <tbody>
            {sale.items.map((i) => (
              <tr key={i.id}><td>{i.medicine_name}</td><td>{i.batch_number}</td><td>{date(i.expiry_date)}</td><td className="num">{i.quantity}</td><td className="num">{inr(i.unit_price)}</td><td className="num">{inr(i.line_total)}</td></tr>
            ))}
            {Number(sale.discount) > 0 && <tr><td colSpan={5} className="num">Subtotal</td><td className="num">{inr(sale.subtotal)}</td></tr>}
            {Number(sale.discount) > 0 && <tr><td colSpan={5} className="num">Discount</td><td className="num">− {inr(sale.discount)}</td></tr>}
            <tr className="grand"><td colSpan={5} className="num">Total</td><td className="num">{inr(sale.total_amount)}</td></tr>
          </tbody>
        </table>
        <p className="muted small" style={{ marginTop: 14 }}>Billed by {sale.sold_by_name || "staff"}. Medicines once sold are returnable only with this bill within 24 hours.</p>
      </div>
    </Modal>
  );
}
