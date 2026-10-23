# Presentation & viva notes

## One-line summary
PharmaTrack is a pharmacy inventory system that tracks medicines batch by batch, sells the earliest-expiring stock first, and uses Grafana to show stock, sales, expiry losses and system health, with email alerts.

## Problem it solves
Small pharmacies lose money to medicines that expire on the shelf, and they run out of fast-moving items because stock lives in a notebook or a basic billing tool. Neither shows *which* strips expire next, and neither warns early enough to act.

## Where each subject appears
| Subject | Where to point in the project |
|---|---|
| **DBMS** | 9-table 3NF schema, FK/UNIQUE/CHECK constraints, PL/pgSQL trigger, 5 views, indexes, row locking, read-only role for Grafana (`docs/DATABASE.md`) |
| **Django** | Models, migrations (including raw SQL), DRF viewsets, JWT auth, role permissions, service layer, management commands, 23 tests |
| **React** | SPA with React Router, context for auth, reusable hooks (`useLoad`, `useForm`), Recharts, billing cart state |
| **HTML/CSS/JS** | Hand-written CSS (no UI framework), responsive layout, print stylesheet for invoices, fetch wrapper with token refresh |
| **Docker** | 7 services + 2 optional profiles in one Compose file, multi-stage frontend build, health checks, named volumes, init scripts |
| **Grafana** | 3 provisioned dashboards (52 panels), PostgreSQL + Prometheus data sources, template variable, 4 alert rules |

## 5-minute demo script
1. **Login** as `pharmacist`. Show the Overview, the **expiry runway** (hover over red marks) and the figures strip.
2. **New bill:** search "Dolo", add 2, then add "Telma" (Rx). Point out that the doctor field becomes required. Create the bill. The invoice shows the **batch number and expiry the system picked (FEFO)**.
3. **Stock & expiry:** that batch's units dropped. Show the *Expired* tab. Sign in as `staff` and **write off** an expired batch.
4. **Alerts:** low stock and expiring lists. Click *Reorder stock*, and the purchase order is pre-filled with low items. Place the order, then **Receive** it with a batch number. The stock appears.
5. **Grafana** (`/grafana`): the Inventory dashboard (value expiring per week, losses), then the Sales dashboard with a category filter. Start `docker compose --profile demo up -d` beforehand so the System dashboard is moving live.
6. **Database:** in `psql`, try to insert a sale item from an expired batch and show the trigger error (`docs/DATABASE.md`).

## Likely questions
**Why PostgreSQL and not MySQL/SQLite?**
It has strong support for PL/pgSQL triggers, `FILTER` aggregates, `generate_series` for the weekly expiry chart, row-level locking, and a first-class Grafana data source.

**What is FEFO and how is it implemented?**
First Expiry, First Out. `services.create_sale()` orders a medicine's non-expired batches by `expiry_date` and takes from the first, spilling into the next batch if needed. Batches are locked with `SELECT … FOR UPDATE` inside one transaction.

**Why both a trigger and Python checks?**
Python gives friendly error messages. The trigger is the guarantee: even a raw SQL insert or a future bug can't sell expired stock or oversell.

**Why is stock not a column on Medicine?**
It would be redundant and could drift. It is derived from batches (`v_medicine_stock`), which also respects expiry.

**How does Grafana get data?**
Two ways. It runs SQL directly on PostgreSQL views as the read-only `grafana_reader` (business data), and it queries Prometheus, which scrapes `/metrics` from Django, postgres-exporter and cAdvisor every 15 s (system data).

**How are alerts sent?**
Grafana alert rules run SQL or PromQL every 5 min (1 min for API down) and notify the email contact point. More channels (Telegram, Slack) can be added in the UI.

**How is it secured?**
JWT auth with role-based permissions on every endpoint. Grafana has a read-only DB user. `/metrics` is not exposed through nginx. Secrets live in `.env`. When published, it runs over Cloudflare HTTPS with Cloudflare Access in front of Grafana and admin.

**How is it deployed?**
`docker compose up -d`. To go public, the `cloudflared` container opens an outbound tunnel to Cloudflare, so the site is served at `https://pharma.yourdomain.com` with no open ports.

**What would you add next?**
Barcode scanning at billing, GST invoice breakdown, returns to supplier, SMS refill reminders for chronic patients, and demand forecasting from sales history for automatic reorder quantities.
