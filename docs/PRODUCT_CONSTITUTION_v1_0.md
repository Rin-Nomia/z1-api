# Continuum 產品憲法 v1.0（Product Constitution）

## 0. 文件定位（唯一母法）

本文件用途只有一個：

**確保 Continuum「對外聲明」與「系統行為」永遠一致。**

本文件優先級高於行銷文案、Demo 文案與簡報話術。  
凡與本文件衝突的表述，一律視為錯位。

---

## 1. 一句話定義（唯一主錨）

**Continuum 是生成式 AI 的發言權治理層（Output Governance Layer）。**

延伸說明：
- Continuum 的核心不是「讓 AI 更會說話」，
- 而是「在不該說話時，讓 AI 降權或停止說話」。

---

## 2. 核心問題（Problem Statement）

在高信任場景（心理健康、金融、醫療、陪伴）中，失敗常見原因不是內容錯誤，而是**發言權錯配**：  
AI 在不該主導的時刻主導了對話。

典型風險型態：
- 過度安慰（Over-comforting）
- 越權引導（Over-guiding）
- 不必要說教（Unsolicited coaching）

商業後果：
- 信任侵蝕
- 靜默流失（Silent Churn）
- 品牌與法務風險上升

---

## 3. Continuum 是什麼（What It Is）

Continuum 是位於輸出端的治理決策層，負責：
1. 評估語境風險（Contextual Integrity）
2. 判斷 AI 是否保有發言主導權
3. 產生唯一且可稽核的治理決策

重要界定：
- Continuum 不是內容創作產品；
- 但在治理決策後，系統可執行最低必要輸出策略（例如 echo / rewrite / intercept）以落實治理。

---

## 4. Continuum 不是什麼（Hard Boundaries）

Continuum 不是：
- ❌ 情緒陪伴 AI
- ❌ 心理諮商或治療工具
- ❌ Prompt 優化器 / 語氣潤飾工具
- ❌ 企圖成為更「像人」的主模型

判斷準則：
- 若展示讓人誤以為 Continuum 在「安慰或引導使用者」，即屬展示錯位。

---

## 5. 唯一治理原則（The One Rule）

**產品價值在治理決策，不在字面改寫。**

- 「沒改字」不代表沒介入
- 「退後一步」本身就是治理行為

---

## 6. 對外決策契約（CIP Decisions）

Continuum 對每次輸出，只產生一個對外決策：

1. **ALLOW**：透明通行（語境穩定，無干預）
2. **GUIDE**：降權治理（AI 不應主導，但不需完全中止）
3. **BLOCK**：強制攔截（風險不可接受，停止原輸出）

---

## 7. 決策映射表（外部三態 vs 內部執行）

| 對外 decision_state | 對內執行 mode | 系統行為 | 稽核重點 |
| --- | --- | --- | --- |
| ALLOW | no-op | 原輸出通過 | 記錄為 pass-through，保留決策證據 |
| GUIDE | suggest | 降權後最小干預（可為 echo/holding） | 必須可證明「未主導、未越權」 |
| GUIDE | repair | 受控改寫以移除越權表述 | 必須可回溯改寫責任與風險理由 |
| BLOCK | block（或 OutOfScope 邊界命中） | 中止原輸出，轉安全流程 | 必須可證明攔截觸發原因與時間 |

約束：
- 對外只允許 `ALLOW / GUIDE / BLOCK`
- `echo`、`rewrite` 僅為 GUIDE 的內部執行型態，不是新決策類別

---

## 8. 治理保證（Governance Guarantees）

1. **No Viewpoint Censorship（不做立場審查）**  
   不依觀點、立場、價值偏好做內容封禁；僅做風險邊界與發言權治理。

2. **No Model Alteration（不改模型本體）**  
   不改動基礎模型權重，不強綁客戶既有模型架構。

3. **No Intent Guessing（不做意圖臆測）**  
   不宣稱理解隱含真意；只依可觀測語境訊號進行治理判斷。

---

## 9. 法務安全措辭（可用 / 禁用）

### 9.1 對外可用措辭（Approved Claims）

- 「Continuum 是輸出端發言權治理層，不是對話模型。」
- 「Continuum 產生可稽核的治理決策：ALLOW / GUIDE / BLOCK。」
- 「Continuum 的目標是降低越權輸出風險，而非提升內容華麗度。」
- 「BLOCK 代表風險攔截與安全流程轉交，不代表臨床判斷。」

### 9.2 禁用措辭（Prohibited Claims）

- 「Continuum 能判斷使用者真正意圖」
- 「Continuum 提供心理治療/醫療建議」
- 「Continuum 保證 100% 阻止所有風險事件」
- 「Continuum 會讓 AI 更懂人、更會安慰人」

---

## 10. 高風險邊界聲明（Regulated Scenarios）

對心理危機、自傷等高風險語境：
- Continuum 的責任是治理與攔截，不是臨床處置；
- 產品需導向預先定義的安全流程（safe flow）；
- 不對外宣稱臨床有效性、診斷能力或治療能力。

---

## 11. UI / Demo 合法範圍

UI 可以：
- 視覺化決策（ALLOW/GUIDE/BLOCK）
- 顯示治理證據（風險理由、攔截與降權結果）
- 顯示可審計資訊（指標、追蹤 id、決策分佈）

UI 不可以暗示：
- Continuum 在扮演情緒陪伴角色
- Continuum 在替使用者做心理或醫療判斷
- Continuum 的價值來自「更會安慰」

原則：**UI 是治理證據層，不是對話角色層。**

---

## 12. 自我一致性檢查（每次改動必過）

改動前請回答：
1. 這次改動是否改變「誰有發言權」？
2. 這次改動是否只在提升治理可理解性與可稽核性？
3. 這次改動是否引入與本憲法衝突的對外承諾？

若第 1 題為「是」、第 3 題為「是」，不得上線。

---

## 13. 對外錨點句（建議固定）

**Continuum 的價值不在它說了什麼，而在它阻止 AI 在不該說話時說話。**

