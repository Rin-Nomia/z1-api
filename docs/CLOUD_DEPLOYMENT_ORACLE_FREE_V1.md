# Continuum Cloud Deployment (Oracle Always Free) v1

## Why Oracle Always Free

For your current architecture (FastAPI + Streamlit C3 + SQLite + reverse proxy), Oracle Always Free is the most practical zero-cost option:

- long-running container workloads
- stable public IP
- full control of ports, TLS, and hardening
- no forced serverless refactor

---

## 0) What you need before starting

- Oracle Cloud account
- one Ubuntu VM (recommended: Ubuntu 22.04, ARM shape VM.Standard.A1.Flex)
- one or two domain names:
  - `api.your-domain.com`
  - `c3.your-domain.com`
- both DNS `A` records pointing to your Oracle VM public IP

---

## 1) Create VM with cloud-init (near one-click)

When creating the Oracle VM:

1. Open **Advanced options**
2. Paste file content from:
   - `deploy/oracle/cloud-init.yaml`
3. Launch VM

That cloud-init will:
- install Docker + Compose plugin
- clone this repo to `/opt/continuum-api`
- create initial `.env` template

---

## 2) Open ports

In Oracle VCN Security List (Ingress):
- `80/tcp`
- `443/tcp`
- `7860/tcp` (optional direct API debug)

SSH (22) remains open for administration.

---

## 3) Fill secrets (single file)

SSH into VM and edit:

```bash
sudo nano /opt/continuum-api/.env
```

Use values from:
- `deploy/oracle/.env.oracle.example`

Mandatory:
- `LOG_SALT`
- `LICENSE_KEY`
- `C3_ADMIN_PASSWORD_HASH` (recommended) or `C3_ADMIN_PASSWORD`
- `C3_BASIC_AUTH_HASH`
- `API_HOSTNAME`
- `C3_HOSTNAME`
- `ACME_EMAIL`

Hash helpers:

```bash
cd /opt/continuum-api
python3 generate_c3_password_hash.py
docker run --rm caddy:2.9.1-alpine caddy hash-password --plaintext 'YourStrongPass!'
```

---

## 4) Add license file

Put encrypted license at:

```bash
/opt/continuum-api/data/license/license.enc
```

---

## 5) Launch stack

```bash
cd /opt/continuum-api
./deploy/oracle/up_oracle_stack.sh
```

This launches:
- `continuum-api`
- `continuum-c3` (private, not directly public)
- `c3-gateway` (HTTPS + BasicAuth + reverse proxy)

---

## 6) Verify

API:
- `https://api.your-domain.com/health`

C3:
- `https://c3.your-domain.com`
  - first: gateway BasicAuth
  - second: C3 admin login

Security target:
- C3 `Security Guards` should show `SALT / HEALTH / HEARTBEAT`

---

## Operational commands

```bash
cd /opt/continuum-api
docker compose -f docker-compose.c3.yml ps
docker compose -f docker-compose.c3.yml logs -f c3-gateway
docker compose -f docker-compose.c3.yml restart continuum-api
```

---

## Current readiness status

Product and control-plane implementation is already complete.  
Remaining go-live tasks are deployment operations only:

1. cloud VM creation
2. DNS binding
3. secret/license provisioning
4. service boot + TLS verification

