# Publishing PharmaTrack on your domain with Cloudflare Tunnel

A Cloudflare Tunnel makes an **outbound** connection from your machine to Cloudflare, and Cloudflare serves your domain over HTTPS through it. You don't need a public IP, open router ports or an SSL certificate. It works the same on a laptop, a home PC or a cloud VM.

```
Visitor ──https──► Cloudflare edge ──tunnel──► cloudflared container ──► frontend (nginx) ──► Django / Grafana
```

## Before you start
- A domain you own (any registrar works, such as GoDaddy, Namecheap or Hostinger).
- A free Cloudflare account.
- PharmaTrack already running locally with `docker compose up -d`.

## Step 1: Add the domain to Cloudflare
1. In the Cloudflare dashboard, choose **Add a domain**, enter `yourdomain.com` and pick the **Free** plan.
2. Cloudflare shows two nameservers, like `xxx.ns.cloudflare.com`.
3. At your registrar, replace the existing nameservers with those two.
4. Wait until Cloudflare marks the domain **Active**. This is usually under an hour, occasionally up to 24.

## Step 2: Create the tunnel
1. Open **Zero Trust** from the Cloudflare sidebar. The first time, choose a team name and the Free plan.
2. Go to **Networks → Tunnels → Create a tunnel**, choose **Cloudflared**, and name it `pharmatrack`.
3. On the install screen, choose **Docker**. Copy only the long token after `--token` in the shown command.
4. Paste it into `.env`:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...
   ```

## Step 3: Add the public hostname
On the tunnel's **Public Hostname** tab (the next screen of the wizard), add:

| Field | Value |
|---|---|
| Subdomain | `pharma` |
| Domain | `yourdomain.com` |
| Service type | `HTTP` |
| URL | `frontend:80` |

One hostname is enough, because nginx inside the stack already routes `/api`, `/admin` and `/grafana`.

> To give Grafana its own subdomain too, add a second hostname, `grafana.yourdomain.com` → `HTTP` → `grafana:3000`. Then set `GF_SERVER_ROOT_URL` for Grafana to that address and remove `GF_SERVER_SERVE_FROM_SUB_PATH`. The single-hostname setup is simpler.

### No card for Zero Trust? Create the tunnel from the command line instead
Zero Trust onboarding can ask for a payment method. Tunnels created with `cloudflared` skip it (only the domain must be on Cloudflare). From the project folder:
```bash
mkdir -p .cloudflared   # git-ignored; holds the login cert and tunnel credentials
cf() { docker run --rm --user "$(id -u):$(id -g)" -e HOME=/work -v "$PWD/.cloudflared:/work/.cloudflared" cloudflare/cloudflared:latest "$@"; }
cf tunnel login                                        # open the printed URL, pick the domain, Authorize
cf tunnel create pharmatrack
cf tunnel route dns pharmatrack pharma.yourdomain.com
cf tunnel token pharmatrack                            # paste into .env as CLOUDFLARE_TUNNEL_TOKEN
```
No public hostname setup is needed: `docker-compose.yml` sets `TUNNEL_URL=http://frontend:80` for this case.

## Step 4: Tell the app its public address
Edit `.env`:
```
PUBLIC_URL=https://pharma.yourdomain.com
DJANGO_ALLOWED_HOSTS=pharma.yourdomain.com,localhost,127.0.0.1,backend
GRAFANA_ANONYMOUS_VIEWER=false
```

## Step 5: Start everything with the tunnel
```bash
docker compose --profile tunnel up -d
docker compose logs cloudflared      # look for "Registered tunnel connection"
```
Open `https://pharma.yourdomain.com`. The tunnel page in Zero Trust should show **HEALTHY**.

## Step 6: Lock it down (recommended)
- **Change the demo passwords** (admin/pharmacist/staff and the Grafana admin), or set `SEED_DEMO_DATA=false` on a fresh database and create your own users.
- **Protect Grafana and Django admin with Cloudflare Access** (free for up to 50 users):
  1. Go to Zero Trust → **Access → Applications → Add an application → Self-hosted**.
  2. Set the application domain to `pharma.yourdomain.com` with path `grafana`, and add a second one with path `admin`.
  3. Add a policy: **Allow**, *Emails*, then your email and your examiner's.
  4. Visitors to those paths now have to confirm their email with a one-time code before Grafana or the admin even loads.
- In Cloudflare **SSL/TLS → Edge Certificates**, turn on **Always Use HTTPS**.

## Keeping it online
The site is up only while the machine running Docker is on. For 24/7 hosting, run the same project on a small cloud VM (Oracle Cloud Free Tier, AWS, Azure for Students, Google Cloud). Install Docker, copy the folder, then use the same `.env` and the same command. Containers use `restart: unless-stopped`, so they come back after a reboot as long as Docker starts on boot.

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Cloudflare error 1033 | The tunnel isn't connected. Check `docker compose logs cloudflared` and the token |
| Cloudflare error 502 | The tunnel is up but `frontend:80` isn't. Check `docker compose ps` |
| "Bad Request (400)" from Django | The domain is missing from `DJANGO_ALLOWED_HOSTS` |
| Grafana redirects to `localhost` | `PUBLIC_URL` isn't set to the https address. Restart Grafana |
| CSRF error in Django admin | `PUBLIC_URL` must match the address in the browser exactly, including `https://` |
