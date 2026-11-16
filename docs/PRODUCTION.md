# Production Deployment Guide

How to run CAD-to-Cutlist Engine in production with Docker.

## Quick start

```bash
# 1. Configure
cp .env.example .env
# edit .env — set CUTLIST_API_TOKEN (and GROQ_API_KEY if you want AI features)

# 2. Build & run
docker compose up -d --build

# 3. Verify
curl http://localhost:8000/healthz
```

Open `http://localhost:8000/` — the review SPA is served by the API container.
No separate web server needed.

## What the image contains

| Stage | Base | Purpose |
|---|---|---|
| `frontend` | `node:22-alpine` | `npm ci` + `npm run build` → static SPA in `dist/` |
| `runtime` | `python:3.12-slim` | Engine + `[cad,ai]` extras, built frontend, non-root user |

- The app runs as the **`cutlist`** system user (not root).
- Frontend is copied to `/app/frontend/dist` and wired to the server via
  `CUTLIST_FRONTEND_DIR` (new env var supported by `server.py`).
- Runs as a single uvicorn worker by default (`CUTLIST_WORKERS=1`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CUTLIST_API_TOKEN` | *(unset)* | **Set in production.** All `/api/*` routes then require `Authorization: Bearer <token>`. `/healthz` and static SPA stay open. |
| `GROQ_API_KEY` | *(unset)* | Switches on every AI feature (see README, "AI layer"). Optional: everything else works without it, and the web app hides the AI buttons. |
| `CUTLIST_AI_MODEL` | `openai/gpt-oss-120b` | Text model. Change it when the provider retires a model. |
| `CUTLIST_AI_VISION_MODEL` | `qwen/qwen3.8-27b` | Model that reads sketch photos. A preview model at the provider, so the most likely to change. |
| `CUTLIST_AI_SPEECH_MODEL` | `whisper-large-v3-turbo` | Speech-to-text model for voice notes. |
| `CUTLIST_AI_DAILY_LIMIT` | `200` | AI calls per user per day. Held in memory per process, so it resets on restart and is not a billing meter. |
| `CUTLIST_CORS_ORIGINS` | *(any)* | Browser origins allowed to call the API, comma separated. |
| `CUTLIST_RATE_LIMIT` | `on` | `off` disables sign-in and sign-up limits. |
| `CUTLIST_TRUST_PROXY` | *(auto)* | `1` always read the client address from `X-Forwarded-For`, `0` never. |
| `CUTLIST_APP_URL` | *(unset)* | **Set in production.** Public base URL used in verification and password-reset emails. |
| `CUTLIST_MAX_UPLOAD_MB` | `100` | Rejects uploads above this size. |
| `CUTLIST_MAX_TRIANGLES` | `500000` | Rejects geometry too expensive to process. |
| `CUTLIST_SESSION_TTL_HOURS` | `168` | Stale session folders are cleaned on startup. |
| `CUTLIST_SESSION_DIR` | `/data/sessions` | Persistent review sessions + artifacts (volume-backed). |
| `CUTLIST_WORKERS` | `1` | Keep at **1** — see scaling note below. |
| `PORT` | `8000` | Listen port inside the container. |

## Why one worker?

Review sessions are cached in-process and guarded with per-process
`threading.Lock`s; artifacts are rewritten into the session folder on finalize.
The session *data* itself survives restarts (it reloads from
`CUTLIST_SESSION_DIR`), but concurrent same-session finalize calls from two
processes would race. Keep `CUTLIST_WORKERS=1`; the container is CPU-bound
single-request anyway, and concurrency across different users is handled by
uvicorn's async loop + thread locks.

If you must scale horizontally later:

1. Mount the same `cutlist-sessions` volume into N replicas (sessions reload
   from disk in every replica).
2. Front with a reverse proxy that pins a session to one replica
   (sticky routing by `session_id`), or add a lock-file/Redis lock for finalize.

## TLS / reverse proxy

Put a TLS-terminating reverse proxy in front. Two minimal examples:

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name cutlist.example.com;

    ssl_certificate     /etc/letsencrypt/live/cutlist.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cutlist.example.com/privkey.pem;

    client_max_body_size 110M;   # match CUTLIST_MAX_UPLOAD_MB

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;    # heavy geometry can take a while
    }
}
```

### Caddy (automatic HTTPS)

```caddy
cutlist.example.com {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 110MB
    }
}
```

When terminating TLS at the proxy, bind the container port to localhost only:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

## CORS

By default the API answers browsers from any origin. That is safe here because
sign-in is by bearer token, never a cookie, so another site has nothing to ride
on. To allow only your own site, set `CUTLIST_CORS_ORIGINS` to a comma-separated
list (for example `https://cutlist.example.com`).

## Public-launch safeguards

- **Rate limits.** Sign-in (10 per 5 minutes), sign-up (10 per hour), password
  reset (5 and 10 per hour) and account deletion (5 per hour) are limited per
  client address, in memory per process. Behind a proxy on the same host or Docker
  network the address is read from the last `X-Forwarded-For` entry, which your
  proxy must set (nginx: `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`).
  `CUTLIST_TRUST_PROXY=1` always trusts it, `0` never does, `CUTLIST_RATE_LIMIT=off`
  disables the limits. Add a proxy-level limit for anything stronger.
- **Headers.** Every response carries `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` and `Permissions-Policy`, and `Strict-Transport-Security` when the
  request came over HTTPS (directly or via `X-Forwarded-Proto`). There is no
  Content-Security-Policy yet.
- **Password reset** needs working SMTP and `CUTLIST_APP_URL`: the emailed link is
  `CUTLIST_APP_URL/?reset=TOKEN`, valid for one hour and one use. Without SMTP the link
  is only written to the server log. Existing sign-in tokens stay valid for up to 7 days after a reset.
- **Deleting data.** Users delete a project from their project list and their whole
  account from the Account section; both remove files from storage. The database row and
  files go immediately; copies inside your backups age out on your backup schedule.
- **Legal pages.** `terms.html` and `privacy.html` are served from the frontend's `public/`
  folder. Fill in the `[bracketed]` values and have them reviewed before launch.

## Backups / data to keep

Three things hold state. Back up the first two daily and test a restore.

| What | Volume | Contains |
|---|---|---|
| Database | `cutlist-db` (Postgres) | accounts, projects, plans, offcuts |
| Files | `cutlist-storage` | uploaded models and every generated file |
| Sessions | `cutlist-sessions` | short-lived review sessions (optional) |

```bash
# Database (a consistent dump, no downtime)
docker exec cutlist-db pg_dump -U cutlist cutlist | gzip > cutlist-db-$(date +%F).sql.gz

# Files
docker run --rm -v cutlist-engine_cutlist-storage:/data -v "$PWD:/backup"     alpine tar czf /backup/storage-$(date +%F).tgz -C /data .
```

Restore the dump with `gunzip -c FILE | docker exec -i cutlist-db psql -U cutlist cutlist`
into an empty database. Keep copies off the server. Volume names carry your
compose project prefix; check `docker volume ls`.

## Deploy workflow

```bash
git pull
docker compose build
docker compose up -d        # replaces the container; sessions volume persists
docker compose logs -f      # watch startup
```

The container cleans expired sessions on startup (`CUTLIST_SESSION_TTL_HOURS`).

## Verify the deployment

```bash
curl http://localhost:8000/healthz
# → {"status":"ok", ... "auth_enabled": true}

# Without a token this should now return 401:
curl -i http://localhost:8000/api/process

# With a token:
curl -i -H "Authorization: Bearer $CUTLIST_API_TOKEN" http://localhost:8000/api/process
```

## CLI usage inside Docker

The engine CLI is installed in the image, so ad-hoc jobs can run as:

```bash
docker run --rm -v "$PWD:/work" -w /work cutlist-engine:latest \
    cutlist-engine /work/input.obj --output-dir /work/out --gcode
```
