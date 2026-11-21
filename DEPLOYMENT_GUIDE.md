# Deploying to Google Cloud

The hub keeps its state in one SQLite file, so it runs as **one Compute Engine VM** with a
persistent disk (not Cloud Run, whose filesystem is wiped on every restart). `deploy/gcp/deploy.sh`
creates and updates everything; re-run it to ship new code.

```
participants ──HTTPS──▶ static IP ─▶ VM (Debian 12, e2-medium, asia-south1)
                                       ├─ caddy  :80/:443  Let's Encrypt certificate
                                       └─ hub    :7400     server_7400.py, /data/hub.db (Docker volume)
                                     boot disk snapshotted daily, 7 days kept
```

## What you need

- A GCP project with billing and the Compute Engine API enabled, and `gcloud` logged in (`gcloud auth login`).
- IAP TCP forwarding allowed for your account (`roles/iap.tunnelResourceAccessor`) — the script uses it for SSH,
  so port 22 is never open to the internet.
- Optional: your own domain. Without one the script uses `<static-ip>.sslip.io`, which still gets a real certificate.

## Preflight (creates nothing)

```bash
PROJECT=my-gcp-project ./deploy/gcp/deploy.sh --check
```

It checks the CLI login, project access, billing, required APIs, your event times and the files to ship,
and says whether the VM will be created or updated.

## Deploy

Run from the repository root in Git Bash (Windows), macOS or Linux. On Windows, gcloud uses its bundled
PuTTY for SSH/SCP over IAP; the first run creates an SSH key without prompting.

```bash
PROJECT=my-gcp-project \
EVENT_NAME="Hack Day 2026" \
EVENT_START=2026-12-05T09:00:00+05:30 \
EVENT_END=2026-12-06T09:00:00+05:30 \
./deploy/gcp/deploy.sh
```

Optional variables: `ZONE` (default `asia-south1-a`), `NAME` (`hackathon-hub`), `MACHINE` (`e2-medium`),
`DOMAIN`, `UTC_OFFSET_MINUTES` (330), `REGISTRATION_CODE`.

On first run it writes `deploy/gcp/.env.hub` (git-ignored, mode 600) with a generated **admin token** and
**event code**. Share the event code with participants; keep the admin token with organisers.

The script prints the three URLs. Put `/stage` on the projector and `/join` on the slides.

## Cost (approximate, asia-south1)

e2-medium ≈ US$1/day, static IP and 20 GB disk a few cents a day, snapshots pennies.

## Rehearsed locally (same bundle, same Compose stack, Caddy on `localhost`)

- 100 builders uploading every 20 s **and** 100 browsers polling every 10 s through HTTPS:
  uploads p95 50 ms, 0 failures; leaderboard p95 294 ms, 0 errors. Hub container: ~25 MB RAM.
- Code update (`compose up --build`) and full `down`/`up` keep all data (Docker volume).
- HTTP→HTTPS redirect, HSTS, CSP and the other security headers, event-code gate, admin token reissue
  (old token stops working), `HEAD`/`GET /healthz` for uptime checks.

## Operating during the event

- **Lost token:** `curl -X POST https://<host>/api/admin/reissue -H "X-Admin-Token: $HUB_ADMIN_TOKEN" -d '{"name":"Their Name"}'`
- **Remove a test or abusive entry:** same with `/api/admin/remove`.
- **Logs:** `gcloud compute ssh hackathon-hub --zone asia-south1-a --tunnel-through-iap --command "cd /opt/hub/deploy/gcp && sudo docker compose logs -f hub"`
- **Backup now:** `gcloud compute disks snapshot hackathon-hub --zone asia-south1-a`
- **Dry run before the day:** point `scripts/simulate.py --hub https://<host> --code <event code>` at it, then
  remove the simulated builders (or redeploy to a fresh VM).

## Tear down

```bash
gcloud compute instances delete hackathon-hub --zone asia-south1-a
gcloud compute addresses delete hackathon-hub-ip --region asia-south1
gcloud compute firewall-rules delete hackathon-hub-web hackathon-hub-iap-ssh
gcloud compute resource-policies delete hackathon-hub-daily --region asia-south1
```
