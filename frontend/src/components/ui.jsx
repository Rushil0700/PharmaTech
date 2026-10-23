import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { STATUS_LABEL } from "../format";

// Load data and expose { data, error, loading, reload }.
export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    fnRef.current()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }));
    return () => { alive = false; };
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(reload, deps);
  return { ...state, reload };
}

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="btn ghost small" onClick={onClose} aria-label="Close">Close</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

export function Field({ label, hint, children, full }) {
  return (
    <div className={`field${full ? " full" : ""}`}>
      <label>{label}{children}</label>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export const Notice = ({ kind = "error", children }) => (children ? <div className={`notice ${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div> : null);

export const StatusBadge = ({ status }) => <span className={`badge ${status}`}>{STATUS_LABEL[status] || status}</span>;

export function Loading({ what = "Loading" }) {
  return <div className="empty">{what}…</div>;
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function Pager({ data, page, setPage }) {
  if (!data || (!data.next && !data.previous)) return null;
  const pages = Math.ceil(data.count / 25);
  return (
    <div className="toolbar" style={{ borderTop: "1px solid var(--line)", borderBottom: 0 }}>
      <span className="muted small">Page {page} of {pages} · {data.count} records</span>
      <span className="spacer" />
      <button className="btn small" disabled={!data.previous} onClick={() => setPage(page - 1)}>Previous</button>
      <button className="btn small" disabled={!data.next} onClick={() => setPage(page + 1)}>Next</button>
    </div>
  );
}

// Controlled form helper.
export function useForm(initial) {
  const [values, setValues] = useState(initial);
  const bind = (name, type = "text") => ({
    name,
    value: type === "checkbox" ? undefined : values[name] ?? "",
    checked: type === "checkbox" ? Boolean(values[name]) : undefined,
    type,
    onChange: (e) => setValues((v) => ({ ...v, [name]: type === "checkbox" ? e.target.checked : e.target.value })),
  });
  return { values, setValues, bind };
}
