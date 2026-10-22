# 資料表介面 v3 實作說明

依規格最終版 v3（2026-10-21 15:46）實作。

## 套用範圍

- **使用新架構**：Inventory（`table_ui_hosts.json`）
- **維持舊 maint.js**：系統設定 → 介面文字（`settings_tabs.json` 僅 system_setting）

## 新增／主要檔案

| 檔案 | 說明 |
|------|------|
| `data/maintenance/table_ui_hosts.json` | 新架構掛載清單 |
| `app/static/js/table_ui.js` | 共用 table UI |
| `app/static/css/table_ui.css` | table UI 樣式（含 sticky menu／表頭） |
| `app/services/maint_service.py` | `build_table_ui_meta`、`peek_next_txid` |
| `app/main.py` | `/api/table-ui/{table_key}/meta`、`next-txid` |
| `data/seed/ui_text.json` | Tab／導覽／dirty 等文案 |
| `config/app_config.json` | `table_ui_hosts_path` |

未改動：`app/static/js/maint.js`（ui_text 沿用）。

## 本機驗收

`http://127.0.0.1:8000/page/inventory`  
`http://127.0.0.1:8000/page/system_setting`（應仍為舊 maint）
