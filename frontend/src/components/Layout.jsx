import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";

const Cross = ({ size = 18, color = "#0f4c3a" }) => (
  <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 2h5v5.5H18v5h-5.5V18h-5v-5.5H2v-5h5.5z" fill={color} /></svg>
);

export default function Layout({ children }) {
  const { user, logout, can } = useAuth();
  const [open, setOpen] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const location = useLocation();

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    get("/alerts/").then((a) => setAlertCount(a.counts.low_stock + a.counts.expired + a.counts.expiring_30)).catch(() => {});
  }, [location.pathname]);

  return (
    <div className={`shell${open ? " nav-open" : ""}`}>
      <div className="mobile-bar">
        <button onClick={() => setOpen(true)} aria-label="Open menu">Menu</button>
        <strong>PharmaTrack</strong>
      </div>
      <aside className="sidebar" onClick={(e) => e.target.tagName === "A" && setOpen(false)}>
        <NavLink to="/" className="brand">
          <span className="brand-mark"><Cross /></span>
          <span className="brand-name">PharmaTrack</span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>Overview</NavLink>
          {can("billing") && <NavLink to="/billing">New bill</NavLink>}
          <NavLink to="/alerts">Alerts {alertCount > 0 && <span className="badge bad">{alertCount}</span>}</NavLink>
          <div className="nav-group">Inventory</div>
          <NavLink to="/medicines">Medicines</NavLink>
          <NavLink to="/stock">Stock & expiry</NavLink>
          <NavLink to="/purchase-orders">Purchase orders</NavLink>
          <NavLink to="/suppliers">Suppliers</NavLink>
          <div className="nav-group">Reports</div>
          <NavLink to="/sales">Sales history</NavLink>
          {can("users") && <NavLink to="/users">Users</NavLink>}
        </nav>
        <div className="sidebar-foot">
          <div className="who">{user.first_name || user.username}</div>
          <div className="role">{user.role}</div>
          <button onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main" onClick={() => open && setOpen(false)}>{children}</main>
    </div>
  );
}
