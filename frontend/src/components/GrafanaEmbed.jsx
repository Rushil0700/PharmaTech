import { useState } from "react";

// Grafana is served by the same nginx under /grafana/, so links and the embed
// work identically on localhost and behind a Cloudflare Tunnel.
const GRAFANA = (import.meta.env.VITE_GRAFANA_URL || "/grafana").replace(/\/$/, "");
const BOARDS = [
  { uid: "pharmatrack-inventory", name: "Inventory & expiry", about: "Stock value, low stock, expiry timeline, category mix and losses." },
  { uid: "pharmatrack-sales", name: "Sales", about: "Revenue trend, bills per day, top sellers, payment mix and gross profit." },
  { uid: "pharmatrack-system", name: "System & API", about: "Request rate, response time, errors, database and container resources." },
];

export default function GrafanaEmbed() {
  const [board, setBoard] = useState(BOARDS[0]);
  const url = (b, kiosk) => `${GRAFANA}/d/${b.uid}/?orgId=1&from=now-30d&to=now${kiosk ? "&kiosk" : ""}`;
  return (
    <section className="panel" style={{ overflow: "hidden" }}>
      <div className="panel-head">
        <div className="tabs">
          {BOARDS.map((b) => <button key={b.uid} className={`tab${b.uid === board.uid ? " active" : ""}`} onClick={() => setBoard(b)}>{b.name}</button>)}
        </div>
        <a className="btn small" href={url(board)} target="_blank" rel="noreferrer">Open in Grafana</a>
      </div>
      <p className="muted small" style={{ padding: "10px 18px" }}>{board.about} If the panel below asks you to sign in, use your Grafana login (admin by default) once.</p>
      <iframe key={board.uid} title={`${board.name} dashboard`} src={url(board, true)} style={{ width: "100%", height: "calc(100vh - 160px)", minHeight: 560, border: 0, display: "block" }} />
    </section>
  );
}
