# EVIDENCE_SCHEMA_V1 Technical Specification

Version: `1.0`  
Source of truth: `continuum-api/app.py -> EVIDENCE_SCHEMA_V1` and `build_evidence_v1()`

---

## 1. Purpose

This schema defines the **content-free audit evidence payload** written by Continuum.

Design goals:
- reproducible
- auditable
- privacy-safe (de-identified)

---

## 2. De-identification rules (MUST)

### 2.1 Raw text persistence prohibition

The logger payload MUST NOT persist:
- user raw input text
- original normalized text
- repaired/generated text as raw body

### 2.2 Fingerprint strategy

Raw content is represented only by:
- `input_fp_sha256`
- `output_fp_sha256`
- `input_length`
- `output_length`

### 2.3 Content-derived scrub

Before persistence, metrics/audit are scrubbed to remove content-derived keys, including (not limited to):
- matched/matches/keyword(s)/trigger(s)
- detected_keywords
- oos_matched
- prompt/messages/completion/response_text
- text/input_text/original/normalized/repaired_text
- raw_ai_output/llm_raw_response/llm_raw_output

---

## 3. Required top-level keys

All keys below are required by schema contract:

1. `schema_version` (string)
2. `input_fp_sha256` (string, sha256 hex)
3. `input_length` (integer)
4. `output_fp_sha256` (string, sha256 hex)
5. `output_length` (integer)
6. `freq_type` (string)
7. `mode` (string)
8. `scenario` (string)
9. `confidence` (object)
10. `metrics` (object, content-scrubbed)
11. `audit` (object, content-scrubbed)
12. `llm_used` (boolean or null)
13. `cache_hit` (boolean or null)
14. `model` (string)
15. `usage` (object)
16. `output_source` (string or null)
17. `api_version` (string)
18. `pipeline_version_fingerprint` (string)

---

## 4. Field type contract

| Field | Type | Privacy note |
|---|---|---|
| schema_version | string | version marker only |
| input_fp_sha256 | string | de-identified fingerprint |
| input_length | int | content length only |
| output_fp_sha256 | string | de-identified fingerprint |
| output_length | int | content length only |
| freq_type | string | taxonomy label |
| mode | string | internal execution mode |
| scenario | string | scenario label |
| confidence.final | float [0,1] | no raw content |
| confidence.classifier | float [0,1] | no raw content |
| metrics | object | scrubbed from content-derived keys |
| audit | object | scrubbed from content-derived keys |
| llm_used | bool or null | runtime indicator |
| cache_hit | bool or null | runtime indicator |
| model | string | model name only |
| usage | object | token usage metadata |
| output_source | string or null | output path marker |
| api_version | string | release marker |
| pipeline_version_fingerprint | string | config fingerprint |

---

## 5. Confidence object contract

Required keys:
- `confidence.final`
- `confidence.classifier`

Both fields MUST be numeric and clamped into `[0.0, 1.0]`.

---

## 6. Validation behavior

`validate_evidence_v1()` checks:
- required keys presence
- confidence shape
- key type sanity:
  - `input_length` int
  - `output_length` int
  - `llm_used` bool|null
  - `cache_hit` bool|null
  - `usage` object
  - `audit` object
  - `metrics` object

If validation fails:
- runtime should not crash
- payload is marked with:
  - `schema_valid: false`
  - `schema_errors: [...]`

---

## 7. Compliance statement

This schema is contract-ready for external audit.  
Any breaking change requires schema version increment and migration notice.

