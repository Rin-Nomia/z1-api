# Commercial Billing & License Operations v1

## 1. Required environment variables

### Security baseline (mandatory)

- `LOG_SALT` **(required)**
  - If missing, logger initialization fails and service refuses to start.

### License guard

- `LICENSE_FILE` (default: `license/license.enc`)
- `LICENSE_KEY` **(required for valid license read)**
- `LICENSE_ENFORCEMENT_MODE` (`degrade` or `stop`, default: `degrade`)
- `LICENSE_CHECK_INTERVAL_SECONDS` (default: `3600`)

### Usage summary signing

- `USAGE_SIGNING_KEY` (optional)
  - If omitted, `LOG_SALT` is used for HMAC signature.

---

## 2. Encrypted license file format

`LICENSE_FILE` should be JSON envelope:

```json
{
  "version": "1.0",
  "nonce_b64": "...",
  "ciphertext_b64": "...",
  "signature_hex": "..."
}
```

Decrypted payload must include:

```json
{
  "license_id": "customer-001",
  "expiry_date": "2026-12-31",
  "quota_limit": 100000
}
```

Validation rules:
- `expiry_date` must be ISO date (`YYYY-MM-DD`)
- `quota_limit` must be integer >= 0
- service becomes invalid if expired or quota exceeded

Generation helper:

```bash
python scripts/generate_license_file.py \
  --output license/license.enc \
  --key "$LICENSE_KEY" \
  --license-id customer-acme \
  --expiry-date 2026-12-31 \
  --quota-limit 100000
```

---

## 3. Signed usage summary outputs

Continuum logger maintains content-free counters and emits:

- `logs/usage/<YYYY-MM>.summary.json`
- `logs/usage/<YYYY-MM>.summary.sig`

Signature algorithm:
- `HMAC-SHA256`

Summary contains:
- month
- analysis_count
- feedback_count
- total_events
- content_free marker

No raw user text is included.

---

## 4. How to generate monthly summary for annual reconciliation

### Option A: API trigger (recommended)

```bash
POST /api/v1/billing/usage-summary
```

Optional query param:
- `month=YYYY-MM`

Response includes:
- summary file path
- signature file path
- signature digest
- monthly counts

### Option B: automatic generation

Monthly summary is auto-finalized on:
- month rollover
- service shutdown

---

## 5. Annual reconciliation workflow

1. Collect all `logs/usage/*.summary.json` and matching `.sig`
2. Verify signature integrity with `USAGE_SIGNING_KEY` (or `LOG_SALT` fallback)
3. Aggregate monthly totals for annual invoice
4. Store verification records with finance/audit archive

Signature verification helper:

```bash
python scripts/verify_usage_summary_sig.py \
  --summary logs/usage/2026-02.summary.json \
  --sig logs/usage/2026-02.summary.sig \
  --key "$USAGE_SIGNING_KEY"
```

---

## 6. Operational notes

- In `degrade` mode, invalid license blocks analyze calls with license error.
- In `stop` mode, invalid license halts service processing.
- Health/status endpoints expose current license status for observability.

