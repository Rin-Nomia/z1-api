---
title: Continuum API
emoji: 💎
colorFrom: blue
colorTo: purple
sdk: docker
sdk_version: "{{sdkVersion}}"
app_file: app.py
pinned: false
---

# Continuum API — RIN Protocol

**Tone Misalignment Firewall**  
語氣錯頻辨識 × 節奏修復 API

Continuum is **not** a sentiment analyzer.  
It is a **tone safety layer** designed to prevent conversational breakdowns caused by misaligned tone, rhythm, or pressure — especially in empathic or companion-style AI systems.

---

## 🧠 What This System Does (Plain Language)

Given a **single sentence**, Continuum will:

1. **Normalize and gate the input** (length, language, safety checks)
2. **Analyze rhythm and emotional pressure** (speed, intensity, pause patterns)
3. **Classify tone misalignment type** (Anxious / Cold / Sharp / Blur / Pushy)
4. **Estimate confidence of the judgment**
5. **Decide whether to**:
   - repair the tone
   - suggest an adjustment
   - or leave it untouched (safe)

This design prevents over-correction and preserves the user’s original intent.

---

## 🎯 Supported Tone Types (MVP Scope)

- **Anxious** — help-seeking, overwhelmed, uncertainty
- **Cold** — detached, withdrawn, disengaged
- **Sharp** — harsh, commanding, high-pressure
- **Blur** — vague, ambiguous, unclear
- **Pushy** — pressing, demanding, urgency-driven

> Neutral or safe tone is explicitly supported and will **not** be modified.

---

## 🧪 Decision Contract (Public API)

Public responses are normalized to one governance decision:

- **ALLOW** → tone is safe, pass-through behavior
- **GUIDE** → constrained guidance / rewrite path applied
- **BLOCK** → out-of-scope or hard safety boundary

> Internal pipeline modes (`repair` / `suggest` / `no-op` / `block`) remain runtime truth,  
> but external API clients should consume `decision_state` only.

---

## 🏗️ Architecture Overview

Input Text  
↓  
Normalization & Length Gate  
↓  
Out-of-Scope Safety Gate (crisis/self-harm)  
↓  
Rhythm Analysis (speed / emotion / pause)  
↓  
Tone Classification (rule-based + margin confidence)  
↓  
Confidence Calibration (rhythm-aware)  
↓  
Router  
├── repair (high confidence)  
├── suggest (medium confidence)  
└── no-op (safe / neutral)  
↓  
Output

---

## 🚫 What This System Explicitly Does NOT Do

Continuum is **intentionally limited** by design.

It does **not** perform:

- ❌ Sentiment scoring (positive / negative)
- ❌ Intent guessing or hidden-meaning inference
- ❌ Psychological diagnosis or mental health evaluation
- ❌ Multi-turn memory or long-term user profiling
- ❌ Clinical or therapeutic intervention

These are **out of scope** for the MVP.

---

## 🛑 Safety & Capability Boundaries (Important)

Continuum is **not designed** to handle:

- Suicidal ideation or immediate self-harm risk
- Severe mental health crises
- Situations requiring emergency intervention or clinical judgment

In such cases, the system will trigger an **Out-of-Scope Safety Gate** and return:

- `decision_state: "BLOCK"`
- `freq_type: "OutOfScope"`
- `scenario: "crisis_out_of_scope"`
- `repaired_text: ""`

> **Design principle:**  
> Continuum only intervenes where **tone affects AI response quality**,  
> but **does not cross into crisis or medical territory**.

It is a **preventive, non-therapeutic tone repair layer**, meant to improve conversational safety — not replace crisis systems.

---

## 🧩 Design Philosophy

- Explainable over powerful
- Predictable over clever
- Safety gates over maximal recall
- User voice preserved at all times

Continuum is designed as a **pre-LLM tone firewall**, not a replacement for the model itself.

---

## 🚀 API Endpoints

### Health Check

```bash
GET /health
```

### Analyze Single Sentence

```bash
POST /api/v1/analyze
Body:
{
  "text": "your input text"
}
Response Example:
{
  "decision_state": "GUIDE",
  "freq_type": "Anxious",
  "confidence_final": 0.73,
  "confidence_classifier": 0.66,
  "scenario": "general",
  "repaired_text": "Let's slow this down and clarify one step at a time.",
  "repair_note": null,
  "privacy_guard_ok": true
}
```

### Operations Metrics

```bash
GET /api/v1/ops/metrics
```

Returns aggregated operability indicators:
- decision_state distribution
- p50/p95/p99 latency
- llm usage rate
- out-of-scope hit rate

⸻

🔄 Sync & Deployment

This repository automatically syncs pipeline, core logic, and configs from:
	•	https://github.com/Rin-Nomia/z1_mvp

⚠️ Do not edit synced files directly.
All logic changes should be made in z1_mvp.

⸻

🛣️ Phase 2 (Out of Scope)

The following capabilities are intentionally excluded from the MVP:
	•	Multi-label tone blending
	•	Hidden meaning inference
	•	Relationship or long-term context awareness
	•	Multi-turn conversation repair
	•	Culture-specific tone policies

These will only be introduced behind explicit feature gates.

⸻

🔗 Links
	•	z1_mvp: https://github.com/Rin-Nomia/z1_mvp
	•	Playground: https://rin-nomia.github.io/continuum-api/playground.html
	•	API Docs: /docs
	•	Product Constitution v1.0: docs/PRODUCT_CONSTITUTION_v1_0.md
	•	Product Constitution (External) v1.0: docs/PRODUCT_CONSTITUTION_EXTERNAL_v1_0.md
	•	Evidence Schema v1.0: docs/EVIDENCE_SCHEMA_V1.md

⸻

RIN Protocol — Continuum
Tone safety before intelligence
Built by Rin Nomia