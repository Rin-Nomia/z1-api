# Continuum Cloud Deployment (Render) v1

## Why Render (for solo developer operations)

Recommended platform: **Render**

Reason:
- GitHub push -> auto deploy
- fixed HTTPS URL out-of-the-box
- supports Docker image services
- easy secret management for `LOG_SALT`, `LICENSE_KEY`, admin secrets
- low ops burden compared with self-managed VM

One-click (Blueprint) link:

`https://render.com/deploy?repo=https://github.com/Rin-Nomia/continuum-api`

Required file already prepared:
- `render.yaml`

---

## Target architecture

```
Internet (HTTPS)
   |
   v
[Render Web Service] c3-gateway (Caddy, TLS + BasicAuth)
   |                        \
   | private network         \--> [Render Web Service] continuum-api
   v
[Render Private Service] continuum-c3 (Streamlit, in-app admin auth)
```

Security notes:
- `continuum-c3` is private-only (no direct public ingress)
- C3 is protected by **double auth**
  1) gateway BasicAuth
  2) C3 admin password (prefer hash mode)
- TLS is terminated by public HTTPS edge + Caddy route policy

---

## 1) Build container images locally

```bash
docker build -f Dockerfile.api -t continuum-api:latest .
docker build -f Dockerfile.c3 -t continuum-c3:latest .
```

Or run all services (API + C3 + TLS gateway) locally:

```bash
docker compose -f docker-compose.c3.yml up -d --build
```

---

## 2) Required secrets

Mandatory:
- `LOG_SALT`
- `LICENSE_KEY`
- `C3_ADMIN_PASSWORD_HASH` (recommended) or `C3_ADMIN_PASSWORD`
- `C3_BASIC_AUTH_HASH` (for Caddy BasicAuth)

Optional:
- `USAGE_SIGNING_KEY` (fallback: `LOG_SALT`)
- `LICENSE_ENFORCEMENT_MODE` (`degrade` / `stop`)
- `C3_LOGIN_MAX_ATTEMPTS` (default 5)
- `C3_LOCKOUT_SECONDS` (default 900)
- `C3_SESSION_TTL_SECONDS` (default 1800)

Generate C3 hash:

```bash
python3 generate_c3_password_hash.py
```

Generate Caddy basic-auth hash:

```bash
docker run --rm caddy:2.9.1-alpine caddy hash-password --plaintext 'YourStrongAdminPass!'
```

---

## 3) Render service setup

### Service A: `continuum-api` (Web Service)
- Dockerfile: `Dockerfile.api`
- Internal port: `8000`
- Public URL example: `https://continuum-api.onrender.com`
- Mount persistent disk to `/data` (for shared logs/license if needed)

### Service B: `continuum-c3` (Private Service)
- Dockerfile: `Dockerfile.c3`
- Internal port: `8501`
- No public route
- Mount persistent disk to `/data`

### Service C: `c3-gateway` (Web Service, public)
- Image: `caddy:2.9.1-alpine`
- Start command: `caddy run --config /etc/caddy/Caddyfile --adapter caddyfile`
- Mount file: `deploy/caddy/Caddyfile` -> `/etc/caddy/Caddyfile`
- Set env:
  - `C3_HOSTNAME=your-c3-domain.example.com`
  - `API_HOSTNAME=your-api-domain.example.com`
  - `C3_BASIC_AUTH_USER=admin`
  - `C3_BASIC_AUTH_HASH=<output from caddy hash-password>`
  - `ACME_EMAIL=<your-email>`

---

## 4) Endpoint policy

- Public API endpoint (HTTPS): `https://<API_HOSTNAME>/api/v1/analyze`
- Public C3 endpoint (HTTPS): `https://<C3_HOSTNAME>/`
- `8501` is never exposed to public internet directly

---

## 5) Verification checklist

1. Open C3 public URL -> must prompt BasicAuth
2. After BasicAuth, C3 login screen appears -> requires admin password
3. Wrong C3 password repeatedly -> lockout triggers
4. Browser shows HTTPS lock icon
5. In C3, `Security Guards` shows SALT / HEALTH / HEARTBEAT

