const inrFmt = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const inrShort = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

export const inr = (v) => inrFmt.format(Number(v || 0));
export const inr0 = (v) => inrShort.format(Number(v || 0));
export const date = (v) => (v ? dateFmt.format(new Date(v.length === 10 ? `${v}T00:00:00` : v)) : "—");
export const dateTime = (v) => (v ? dateTimeFmt.format(new Date(v)) : "—");
export const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
export const addDaysISO = (iso, days) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

export function daysLabel(days) {
  if (days < 0) return `Expired ${-days} day${days === -1 ? "" : "s"} ago`;
  if (days === 0) return "Expires today";
  return `${days} day${days === 1 ? "" : "s"} left`;
}

export function expiryStatus(days) {
  if (days < 0) return "expired";
  if (days <= 30) return "critical";
  if (days <= 90) return "warning";
  return "ok";
}

export const STATUS_LABEL = { expired: "Expired", critical: "Under 30 days", warning: "Under 90 days", ok: "Good" };
