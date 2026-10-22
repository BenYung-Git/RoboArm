# Inventory 存貨管理 — 交付說明

日期：2026-10-21  
範圍：存貨主表 CRUD＋統一檔案維護規則（不接真機、不含出入庫／盤點／Connect）

---

## 1. 修改／新增檔案

| 檔案 | 說明 |
|------|------|
| `app/storage/sqlite_store.py` | 新增 `run_transaction`（`BEGIN IMMEDIATE`） |
| `app/services/ui_service.py` | `inventory` schema、menu upsert、多 host maint tabs |
| `app/services/maint_service.py` | 共用 CRUD 強化（select/number、交易內 TxId、文案） |
| `app/static/js/maint.js` | 共用檢視／新增／編輯／復制狀態、確認、dirty |
| `app/static/css/app.css` | 工具列文字標籤、狀態色、選列、唯讀欄 |
| `app/templates/page.html` | 單一 tab 時隱藏 tabs 列 |
| `data/maintenance/tables.json` | 新增 `inventory` 欄位定義 |
| `data/maintenance/settings_tabs.json` | 改為 `hosts[]`（system_setting + inventory） |
| `data/seed/menus.json` | 新增 inventory（sort_order=5，最底） |
| `data/seed/ui_text.json` | 選單／欄位／確認／復制等三語 |
| `delivery/inventory/01_list.png` | 清單畫面 |
| `delivery/inventory/02_edit.png` | 編輯畫面 |
| `data/RoboArm.db.bak_*` | 變更前資料庫備份 |

未改：虛擬 demo 相關 JS／服務；未新增依賴；未 commit／push。

---

## 2. 資料表結構與 migration

### 備份

啟動／實作前已複製：

`data/RoboArm.db.bak_yyyyMMdd_HHmmss`

### 結構（SQLite，可重複執行）

`UiService.ensure_inventory_schema()`：

```sql
CREATE TABLE IF NOT EXISTS inventory (
  TxId INTEGER PRIMARY KEY,
  ItemCode TEXT NOT NULL DEFAULT '',
  ItemName TEXT NOT NULL,
  Category TEXT NOT NULL DEFAULT '',
  Brand TEXT NOT NULL DEFAULT '',
  Model TEXT NOT NULL DEFAULT '',
  SerialNo TEXT NOT NULL DEFAULT '',
  Quantity REAL,
  Unit TEXT NOT NULL DEFAULT '',
  Location TEXT NOT NULL DEFAULT '',
  dimensions TEXT NOT NULL DEFAULT '',
  isDisable INTEGER NOT NULL DEFAULT 0,
  Remark TEXT NOT NULL DEFAULT ''
);
```

- `TxId`：INTEGER PK；新增時在交易內 `MAX(TxId)+1`（含失效列，編號不重用）。
- `isDisable`：0/1，預設 0；軟刪除。
- `dimensions`：單一自由文字欄，原文保存。
- `Category`：存代碼（`robot_arm` / `control_box` / `tool` / `other`），UI 三語顯示。

### Menu／文案

- `ensure_seed_menus()`：對 seed **upsert**（既有 DB 也會出現 Inventory）。
- `ui_text` seed：INSERT 新 key／UPDATE 既有 key（既有行為）。

---

## 3. 共用功能說明（最小共用）

沿用既有 `/api/maint/{table_key}/...` 與 `maint.js`，不另起框架：

| 共用項目 | 位置 |
|----------|------|
| 表定義／欄位型別 | `data/maintenance/tables.json` |
| 頁面掛載 maint | `settings_tabs.json` → `hosts[].host_menu_key` |
| TxId 交易編號 | `MaintService.create_row` + `SqliteStore.run_transaction` |
| isDisable 切換 | `toggle_disable` API；前端確認＋狀態文案互換 |
| 工具列 icon＋文字＋tips | `maint.js` `actionButton` |
| 檢視／新增／編輯／復制 | `maint.js` mode：`view` / `add` / `edit` / `copy` |
| 未儲存離開確認 | dirty + `confirm_discard` + `beforeunload` |
| 防重複儲存 | `state.saving` 鎖 |

日後新表：在 `tables.json` 加定義、`settings_tabs` 掛 host、必要時 `CREATE TABLE IF NOT EXISTS` 即可。

---

## 4. 畫面

- 清單：`delivery/inventory/01_list.png`
- 編輯：`delivery/inventory/02_edit.png`

選單最底：**存貨管理 / Inventory**。

---

## 5. 簡短測試結果

| 項目 | 結果 |
|------|------|
| Menu 最底為 inventory／存貨管理 | 通過 |
| 新增 → TxId=1,2,3 遞增 | 通過 |
| 失效後再新增仍用下一號（不重用） | 通過（失效 TxId=1 後下一筆為 3） |
| 編輯更新原列、TxId 不變 | 通過 |
| isDisable 切換保留其他欄位 | 通過 |
| dimensions 原文保存 | 通過 |
| 狀態篩選 全部／生效／失效 | API 通過 |
| system_setting／virtual_demo 頁面仍 200 | 通過 |
| 復制／儲存取消／工具列狀態 | 前端已實作；清單／編輯畫面已截圖 |

本機請再開：`http://127.0.0.1:8000/page/inventory` 做互動驗收。
