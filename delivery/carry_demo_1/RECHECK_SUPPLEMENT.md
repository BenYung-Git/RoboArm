# 本機複驗補充資料（不改功能）

路徑：`delivery/carry_demo_1/`  
截圖：`delivery/carry_demo_1/stages/`  
Descend 最大誤差樣本：`descend_worst_sample.json`

---

## 1. 四項誤差一覽

定義皆在 **Z-up robot** 座標系。`tcp.approach`／`tcp.closing` 為單位向量。

| # | 名稱 | 定義／公式 | 允許上限 | 預檢最大值 | 執行中最大值（含插值） | 最大值階段 |
|---|------|------------|----------|------------|------------------------|------------|
| A | TCP XY 漂移 | `hypot(tcp.x − object.center_xy_m[0], tcp.y − object.center_xy_m[1])` | **0.005 m** (`path_xy_drift_max_m`) | **0.002779 m** | **0.002779 m** | **Descend** |
| B | approach ↔ −Z | `acos(dot(normalize(approach), [0,0,-1])) · 180/π`（度） | **22°** (`path_ang_drift_max_deg`) | **17.5385°** | **17.5385°** | **Descend** |
| C | closing ↔ −X | `acos(dot(normalize(closing), [-1,0,0])) · 180/π`（度） | **22°** (`path_ang_drift_max_deg`) | **17.5385°** | **17.5385°** | **Descend** |
| D | closing ⊥ 物件 Z | `abs(90 − acos(dot(normalize(closing), object.axis_world)) · 180/π)`（度） | **22°** (`path_closing_perp_max_deg`) | **17.5385°** | **17.5385°** | **Descend** |

B／C／D **分開計算、分開記錄**。本場景物件軸為 `[0,0,1]`、目標 closing 為 `[-1,0,0]`；當整架姿態以接近同一旋轉偏離理想 frame 時，三個角度在數值上會非常接近，但仍是三個不同公式。

單點 IK 接受門檻另為：`ik_pos_tol_m=0.004`、`ik_ang_tol_deg=18`（B／C 在求解終點也須 ≤18°）。

---

## 2. Descend 誤差最大處（預檢 waypoint index 8）

資料檔：`descend_worst_sample.json`  
對應畫面：`stages/00_DescendWorst.png`（同一組關節靜態擺姿）

| 項目 | 值 |
|------|-----|
| 約目標 Z | 0.28 m（Descend 索引 8／15） |
| 關節角 (deg) | `[-0.0010, 2.1454, 110.7499, 28.8854, 55.7577, -0.0031]` |
| TCP position (m) | `[0.34737, -0.0000063, 0.28290]` |
| approach | `[-0.30135, 0.0000055, -0.95351]` |
| closing | `[-0.95351, -0.000037, 0.30135]` |
| 物件位姿（Descend 時尚未夾取） | center `[0.35, 0, 0.22]`，axis `[0,0,1]` |
| 該點誤差 | XY 0.00263 m；approach→−Z **17.5385°**；closing→−X **17.5385°**；closing⊥Z **17.5385°** |

---

## 3. JSON 輸出摘要

### `preflight_acceptance.json`
- `ok: true`
- 容差：step 0.01／ik_pos 0.004／xy_drift 0.005／ang 22／ik_max_iter 220
- 預檢最大誤差：見上表（皆 @ Descend）
- 流程階段完整：Home→…→ReturnHome

### `acceptance_runtime.json`
- FK 一致：flange／TCP 誤差 ≈ 0
- Completed：joints = Home，home_err=0，grasped=false，gap=0.095，place 誤差極小，state=`completed`
- 執行中最大誤差與預檢同量級（Descend）
- 中途 E-stop／斷線：物件 Z≈0.265–0.276，grasped 保持，`needs_reset`，延遲 complete 忽略

完整檔案請直接開啟上述兩個 JSON。

---

## 4. 17.54° 來源與觀感

- **來源**：Descend 最差點上，**B、C、D 三者同時約 17.54°**（非只揀其中一項）。  
  該點 approach 含明顯 X 分量（≈−0.30），closing 含明顯 Z 分量（≈+0.30），代表 TCP 相對理想「approach=−Z、closing=−X」有約 **十七度級** 的剛體姿態偏差。
- **是否明顯／不自然**：在示意模型上，側視可見腕部略傾，**不是完全垂直壓下**；仍落在目前 `ik_ang_tol_deg=18` 與路徑 22° 上限內，因此軟體判定通過。  
  **不能稱為「視覺上幾乎無傾角」**；若驗收要求接近垂直夾持，17.5° 應視為偏大，需另訂更嚴上限或改善 IK／路徑，而不是用現況宣稱幾何已優。

---

## 5. 22° 上限依據（如實）

- **不是**已驗證的夾具／物件幾何硬需求。  
- 原提案明確鎖定的是位置類：`cartesian_step_m=0.01`、`ik_tolerance_m=0.004`、`path_xy_drift_max_m=0.005`。  
- `path_ang_drift_max_deg=22`（及同值的 `path_closing_perp_max_deg`）是實作時相對 `ik_ang_tol_deg=18` **再加約 4° 路徑鬆弛** 寫入的監控上限，使垂直段在「單點 IK≤18°、路徑監控略寬」下能完成。  
- **請勿將 22° 視為現場量測或真機幾何驗收標準**；若本機複驗認為傾角不可接受，應下修此上限並重跑，而不是反過來為通過而合理化。

---

## 6. 關鍵階段截圖清單

目錄：`delivery/carry_demo_1/stages/`

| 檔名 | 內容 |
|------|------|
| `00_DescendWorst.png` | Descend 誤差最大關節靜態姿 |
| `01_Descend.png` | Descend |
| `02_Grasp.png` | Grasp（gap 接觸） |
| `03_LiftTop.png` | Lift 頂點（物件抬高） |
| `04_Lower.png` | VerticalLower |
| `05_Release.png` | Release（張開） |
| `06_ReturnHome.png` | ReturnHome |
| `07_Completed.png` | Completed（同 Home 姿） |
| `08a_MidLift_pose.png` | 提升中段姿態 |
| `08_MidLift_Estop.png` | 提升中途 E-stop 狀態面板（Aborted／needs_reset／緊急停止=是） |
| `09_MidLift_Disconnect.png` | 提升中途斷線狀態面板（連線=否／needs_reset／仍 grasped） |

說明：流程中段畫面部分為預檢關節靜態擺姿（避免動畫過快錯過取景）；E-stop／斷線為**實際執行中途中止**的狀態截圖。

**功能碼未改動**；僅新增本補充文件與截圖／樣本 JSON 於 `delivery/`。
