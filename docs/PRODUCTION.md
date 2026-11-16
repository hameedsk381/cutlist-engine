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
| `GROQ_API_KEY` | *(unset)* | Enables `/api/ai/*` (part naming, describe→cutlist, chat). Optional. |
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

`server.py` currently allows `*` origins. When serving the SPA from the same
origin (default in this image) this is harmless, but if you split the frontend
onto its own domain, tighten `allow_origins` to that domain.

## Backups / data to keep

The only state is the sessions volume:

```bash
docker run --rm -v cutlist-engine_cutlist-sessions:/data -v "$PWD:/backup" \
    alpine tar czf /backup/sessions.tgz -C /data .
```

Everything else (code, frontend) is in the image.

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
