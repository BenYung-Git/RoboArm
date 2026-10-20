# RoboArmDemo 專案交接檔

> 用途：資料夾改名／新開 Cursor chat 後，把本檔給 AI 閱讀，即可快速接上專案脈絡。  
> 更新日期：2026-10-20  
> 性質：**虛擬示意 demo，不接真機**；非官方 CAD、非精密模擬。

---

## 1. 專案是什麼

- 名稱：RoboArm（虛擬測試／示意六軸）
- 技術：Python FastAPI + 前端 Three.js 示意模型
- 啟動：在專案根目錄執行 `python run.py`
- 預設：`http://127.0.0.1:8000` → 虛擬測試頁 `/page/virtual_demo`
- 設定：`config/app_config.json`（路徑皆相對專案根；**改資料夾名不影響主程式**）
- 路徑根：`app/paths.py` 的 `PROJECT_ROOT`（依 `__file__` 推算，不硬編碼資料夾名）

Cursor 聊天紀錄綁 **workspace 路徑**。改資料夾名後舊 chat 通常不會自動跟著；請用本檔延續上下文。

---

## 2. 目錄地圖（重要）

| 路徑 | 說明 |
|------|------|
| `run.py` | 啟動入口 |
| `app/main.py` | FastAPI 路由／API |
| `app/services/virtual_demo_service.py` | 虛擬 demo 狀態、連線、E-stop、完成條件 |
| `app/services/ui_service.py` | 三語 UI 文案（seed 可 UPDATE） |
| `app/static/js/virtual_demo.js` | 虛擬測試頁 UI／綁定／倍率 |
| `app/static/js/carry_demo_runner.js` | 示範執行動畫、路徑播放、完成檢查 |
| `app/static/js/arm_kinematics.js` | IK／路徑規劃（含示範2前後搬運） |
| `app/static/js/virtual_demo_3d.js` | Three.js 臂／枱／物件顯示 |
| `data/virtual_demo/config.json` | 型號與 demo JSON 清單 |
| `data/virtual_demo/carry_demo_1.json` | 示範1 |
| `data/virtual_demo/carry_demo_2.json` | 示範2（保留 `demo_key`／檔名） |
| `data/virtual_demo/models/` | `rokae_cr7.json`、`jaka_zu7.json` |
| `data/seed/ui_text.json` | 三語文案種子 |
| `data/RoboArm.db` | SQLite（UI 文案等） |

---

## 3. 示範一覽

### 示範1 — 上下搬運

- `demo_key`：`carry_vertical_1_inplace`
- 檔案：`data/virtual_demo/carry_demo_1.json`
- 顯示名：搬運動作示範1（上下搬運）
- 支援型號：`rokae_cr7`
- 模式：原地垂直夾取／放下

### 示範2 — 前後搬運

- `demo_key`：`carry_front_back_2`（**勿改**）
- 檔案：`carry_demo_2.json`（**勿改檔名**）
- `pattern`：`front_back_transfer`
- 顯示名：`搬運動作示範2（前後搬運 >180°）`  
  - 「>180°」**僅名稱文字**，不因此加旋轉或改路徑語意
- 前枱 pick：`+X`（約 `[0.35, 0]`），後枱 place：`−X`（約 `[-0.30, 0]`）
- Transfer：側向 via（約 `+Y`）避開底座／臂身穿透；keepout 約 `0.2 m`
- 播放倍率（**僅示範2**）：`[×1 正常] [×2] [×3]`  
  - 預設 ×1；執行前／中可切；只改時間不改路徑  
  - 重置示範 → 回 ×1；不影響示範1／手動 moveJ

座標：機器人 **Z-up**；3D 用 `armRoot.rotation.x = -π/2` 映到場景。  
Home（CR7 示意）約為 `[0, -40, 50, 0, 40, 0]`（**不是**直豎棒狀，看起來會略彎）。

---

## 4. 已完成／約定行為

- 連線／斷線、緊急停止／解除（E-stop／斷線立即停，不受倍率影響）
- J1–J6 數字、滑桿、XYZ 標籤與動畫同步
- 物件跟隨夾取；**Release 後凍結世界位姿**，不隨回程移動
- **Completed 條件（須全部成立）**：
  1. 物件在後枱、已解除夾持
  2. 夾具張開並退離
  3. 臂已回 Home
  4. 無未完成動畫／待跑階段  
  中途失敗顯示原因，**不可**把停在中途標成完成

---

## 5. 重要修復紀錄（勿當新需求重做）

1. **物件與臂身重疊／穿透（示範2 Transfer）**  
   - 側向 Cartesian／via + keepout；三種倍率同一路徑，不以快轉掩蓋。

2. **示範2 結束看不到物件、臂未回 Home**  
   - 根因：`RetractPlace` 在關節插值**中途幀**觸發 `runtime_xy_drift`（逾 `path_xy_drift_max_m`），放置後中止。  
   - 修復：路徑誤差只在**路徑點終點**檢查；Release 凍結位姿；長路徑改單次 move-j 連續播放。  
   - 主要檔：`carry_demo_runner.js`

3. **靜默拒絕執行示範**  
   - 連線／E-stop／需重置等須有明確橫幅提示。

4. **UI 文案**  
   - `ui_text.json` seed 啟動時可 UPDATE 既有 key（不僅 INSERT）。

---

## 6. 本機驗收建議

1. `python run.py` → 開 `/page/virtual_demo`
2. 型號選 **ROKAE CR7** → **連線** → 解除 E-stop（若有）
3. 示範2：×1／×2／×3 各跑完整流程  
   前枱夾起 → 搬運 → 後枱放下 → 鬆開 → 退離 → **回 Home**  
   結束物件應在後枱（約 `(-0.30, 0)`，中心 z≈0.22）
4. 順便確認示範1仍正常
5. 強制重新整理（JS 有 `?v=` cache bust）

---

## 7. 明確不要做的事（延續既有指令）

- 不接真機、不執行 Git commit／push（除非使用者明確要求）
- 不新增依賴；不改模型造型／相機預設來掩蓋問題
- 不靠快轉或隱藏物件掩蓋路徑／穿透問題
- 使用者說「只回覆／不要修改」時：只回答、不改檔、不跑會寫入的指令

---

## 8. 給新 chat 的開場提示（可複製）

```
請先閱讀專案根目錄 PROJECT_HANDOFF.md，依其中現況與約定接續工作。
本專案為虛擬機械臂示意（不接真機）。改動請最小必要，並用繁體中文回覆。
```

---

## 9. 狀態備註（截至交接日）

- 專案目錄當時可能尚**不是** git repo，或尚未做過 commit。
- 少數臨時檔（如 `tmp_restart.py`）含絕對路徑 `c:\RoboArmDemo`；改名後若還用那些腳本需手動改。
- 主程式與 `data/` 皆相對路徑，**改 folder 名可正常執行**。
