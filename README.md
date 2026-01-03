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

Tone Rhythm Repair Module  
自動從 z1_mvp 同步並部署

## 🏗️ 架構
```
continuum-api (本 repo)
  ├── app.py              ← 你建立的
  ├── requirements.txt    ← 你建立的
  └── .github/workflows/  ← 你建立的

自動同步 (GitHub Actions)：
  ├── pipeline/           ← 從 z1_mvp 複製
  ├── core/               ← 從 z1_mvp 複製
  └── configs/            ← 從 z1_mvp 複製
```

## 📊 系統狀態

- **準確率：** 95%（基於 Rin 對齊度測試）
- **支援語氣：** Anxious, Cold, Sharp, Blur, Pushy
- **修復引擎：** Claude Haiku (LLM) + 關鍵字替換 (Fallback)
- **場景偵測：** 4 種場景（客服、社交、內部溝通、商業）

## 🚀 API 端點

### 健康檢查
```bash
GET https://rinnomia-continuum-api.hf.space/health
```

### 單句分析
```bash
POST https://rinnomia-continuum-api.hf.space/api/v1/analyze

{
  "text": "你的文字"
}
```

**回傳範例：**
```json
{
  "original": "你的文字",
  "freq_type": "Sharp",
  "confidence": 0.85,
  "scenario": "internal_communication",
  "repaired_text": "修復後的文字"
}
```

## 📖 API 文件

部署後訪問：
- Swagger UI: `https://rinnomia-continuum-api.hf.space/docs`
- ReDoc: `https://rinnomia-continuum-api.hf.space/redoc`

## ⚙️ 設定步驟

### 1. 建立 HuggingFace Space

1. 去 https://huggingface.co/spaces
2. 點 "Create new Space"
3. 名稱：`continuum-api`
4. SDK：選 `Docker`
5. Visibility: Public
6. Create

### 2. 確認 Secrets

在本 repo 的 **Settings → Secrets → Actions** 確認有這些：

- ✅ `GH_PAT`：GitHub Token（已有）
- ✅ `HF_TOKEN`：HuggingFace Token（已有）
- ✅ `ANTHROPIC_API_KEY`：Claude API Key（已有）

### 3. 觸發部署

1. 進入 **Actions** 頁籤
2. 選擇 "同步 z1_mvp 並部署 Continuum API"
3. 點 **Run workflow**
4. 等待 5-10 分鐘

## 🔄 自動同步機制

- **觸發條件：** 每次 push 到 main branch
- **同步內容：** 自動從 `Rin-Nomia/z1_mvp` 複製最新的 pipeline, core, configs
- **優點：** z1_mvp 更新後，API 也自動更新

## 🧪 測試
```bash
# 測試健康檢查
curl https://rinnomia-continuum-api.hf.space/health

# 測試分析
curl -X POST https://rinnomia-continuum-api.hf.space/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "測試文字"}'
```

## ⚠️ 注意事項

- **不要手動編輯** pipeline, core, configs（會被覆蓋）
- 要改功能請去 **z1_mvp** 改，然後會自動同步過來
- API 使用 z1_mvp 的完整 Pipeline，包含 LLM 修復

## 📊 效能指標

- 單次分析：~1-2 秒
- 信心值門檻：0.2（使用 LLM）
- 速率限制：50 req/min
- 快取：24 小時 TTL

## 🔗 相關連結

- z1_mvp repo: https://github.com/Rin-Nomia/z1_mvp
- HuggingFace Space: https://huggingface.co/spaces/RinNomia/continuum-api
- API Docs: https://rinnomia-continuum-api.hf.space/docs
- Playground: https://rin-nomia.github.io/continuum-api/playground.html

---

**RIN Protocol — Continuum**  
Built with ❤️ by Rin | Powered by Claude Haiku 4
