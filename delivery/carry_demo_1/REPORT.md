# 搬運動作示範1 — 容差／姿態／Completed／中途停止 修正報告

## 1. 容差變更追查（根因）

相對原提案：

| 參數 | 原提案 | 先前交付 | 本次 |
|------|--------|----------|------|
| `cartesian_step_m` | 0.01 | 0.012 | **0.01（已恢復）** |
| `ik_pos_tol_m` | 0.004 | 0.005 | **0.004（已恢復）** |
| `path_xy_drift_max_m` | 0.005 | 0.008 | **0.005（已恢復）** |
| `ik_max_iter` | 40 | 220 | **220（保留）** |

**變更原因（先前錯誤放寬）**：當時 IK 為「僅位置雅可比 + 姿態只做 seed／事後門檻」（方法名甚至寫成 `oriented_seed_position_ik_monitor_ori`）。在位置收斂邊界附近，為讓路徑「通過」而私下加大步距與容差。

**`ik_max_iter` 保留 220 的理由**：姿態納入 DLS 任務後，單點收斂需要更多迭代；這不是放寬位置／路徑容差，而是求解器迭代上限。已寫入 JSON `motion.ik_max_iter_note`。

**原精度重測結果**：**通過**（見 `preflight_acceptance.json`）。修正姿態參與求解後，無需放寬上述三項。

---

## 2. 姿態約束核實與修正

### 根因
舊 `solveIk` 的雅可比僅 3×6（位置）。`approach`／`closing` 只用於：
- seed 過濾
- 迭代結束時的接受條件
- 偶發的步進軟拒絕  

**未進入誤差向量與雅可比**，不符合「姿態必須參與 IK」。

### 修正
改為 **pose-in-loop DLS**：任務誤差 = 位置(3) + 由 approach／closing 對齊構成的姿态 ω(3)；數值雅可比 6×6。方法改記為 `pose_in_loop_dls_ik`。

### 四項誤差（分開定義，不可混用）

| 名稱 | 公式 | 上限 |
|------|------|------|
| TCP XY 漂移 | `hypot(tcp.x−obj.xy[0], tcp.y−obj.xy[1])` | `path_xy_drift_max_m`=0.005 |
| approach ↔ −Z | `acos(dot(approach,[0,0,-1]))·180/π` | `path_ang_drift_max_deg`=22 |
| closing ↔ −X | `acos(dot(closing,[-1,0,0]))·180/π` | 同上 22 |
| closing ⊥ 物件 Z | `abs(90−acos(dot(closing,object.axis))·180/π)` | `path_closing_perp_max_deg`=22 |

後兩項獨立計算；本場景物件軸為 +Z、目標 closing 為 −X 時數值可能接近，但仍分欄記錄。

### 修正前後（垂直固定 XY 段最大誤差）

| | 先前交付（放寬容差＋僅監控姿態） | 本次（原精度＋姿態入環） |
|--|--|--|
| max XY | 0.0039 m（限 0.008） | **0.0028 m**（限 0.005）@ Descend |
| approach→−Z | 8.6°（混用 closing） | **17.54°** @ Descend |
| closing→−X | （與上混用） | **17.54°** @ Descend |
| closing⊥Z | （未分開） | **17.54°** @ Descend |

預檢與執行中（含動畫插值幀）最大值相同量級，階段均為 **Descend**。執行監控在 `moveJoints` 的每一插值幀執行，不僅 waypoint 端點。

---

## 3. Completed 條件

Completed 前同時檢查（runner + service）：

- 放置檢查已通過（實際物件位姿，不瞬移）
- `grasped=false`，`gap=gap_fully_open_m`
- 關節相對 `home_joints_deg`：`home_joint_tol_deg`=0.5°
- `is_moving=false`
- `demo_run_state` 仍為 `running`（非 abort／needs_reset）

### 本次完成當刻

| 欄位 | 值 |
|------|-----|
| joints | `[0, -40, 50, 0, 40, 0]`（Home 誤差 0°） |
| object | ≈`(0.350014, 0, 0.219961)`，axis `[0,0,1]` |
| place | bottomErr≈3.9e-5 m，xyErr≈1.4e-5 m，tilt=0° |
| grasped / gap | false / 0.095 |
| is_moving / state | false / **completed** |

---

## 4. 提升中途停止

| 測試 | 物件 Z | grasped | gap | state | 結果 |
|------|--------|--------|-----|-------|------|
| E-stop＠VerticalLift | ≈0.265 m | true | 0.071 | needs_reset | 保持關節／位姿／夾持；不可重跑 |
| 斷線＠VerticalLift | ≈0.265 m | true | 0.071 | needs_reset | 同上；connected=false |
| 延遲 complete-motion | — | — | — | needs_reset | `motion_ignored=true`，關節未被覆寫 |

（提升半高目標約 0.28 m；因動畫幀取樣，實測中止點約 0.265 m。未標 Completed。）

---

## 5. 修改檔案

- `data/virtual_demo/carry_demo_1.json`
- `app/static/js/arm_kinematics.js`
- `app/static/js/carry_demo_runner.js`
- `app/static/js/virtual_demo.js`
- `app/services/virtual_demo_service.py`
- `app/main.py`
- `scripts/test_carry_acceptance.mjs`
- `scripts/test_carry_preflight.mjs`（沿用）
- `delivery/carry_demo_1/*`

## 可重跑測試命令

```bat
cd /d c:\RoboArmDemo
set PYTHONIOENCODING=utf-8
node scripts/test_carry_acceptance.mjs
```

完整輸出：`delivery/carry_demo_1/preflight_acceptance.json`  
執行中／Completed／中途停止：`delivery/carry_demo_1/acceptance_runtime.json`

瀏覽器手動：連線 → 選「搬運動作示範1」→ 執行示範；另於 VerticalLift 中段按 E-stop／斷線。

## 錄影限制

本環境**無法提供完整操作錄影檔**。驗證改以：

1. Node 預檢 JSON 全文輸出  
2. 瀏覽器 CDP 逐步狀態快照（`acceptance_runtime.json`）  
3. 畫面截圖（`01`～`05_after_midlift_abort.png`）

請於本機自行錄影複驗 UI 流程。

---

**等待驗收。** 未執行 Git commit／push；未啟用 Zu7；未接真機；未新增依賴。
