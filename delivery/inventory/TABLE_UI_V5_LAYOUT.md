# 資料表 UI v5 — 版面設定實作說明

依規格最終版 v5（2026-10-22 11:30）增量實作。

## 套用範圍

- table_ui（Inventory 及日後 `table_ui_hosts.json` 新表）
- `maint.js`／ui_text：**未改**

## 新增／主要檔案

| 檔案 | 說明 |
|------|------|
| `app/services/table_layout_service.py` | 版面設定服務（schema／預設／儲存） |
| `data/maintenance/zebra_colors.json` | 間隔行顏色（key + Translation + css） |
| `app/static/js/table_ui.js` | 第 5 Tab、版面設定、List 欄位／zebra／header 排序 |
| `app/static/css/table_ui.css` | zebra／layout 樣式 |
| `data/seed/ui_text.json` | 版面／zebra／欄位說明文案 |
| `data/maintenance/tables.json` | inventory 各欄 `desc_key` |
| `app/main.py` | `/api/table-ui/{key}/layout`、`/rows` |

## 資料表

- `ui_table_settings`、`ui_table_columns`（標準 TxId／isDisable／Remark + 時間戳）
- 啟動時 `CREATE TABLE IF NOT EXISTS`；首次開啟 inventory 自動建預設版面

## 本機驗收

1. 重啟 `python run.py`，強制重新整理
2. `/page/inventory`：工具列「版面設定」icon → 第 5 Tab
3. 調整 zebra／欄位 visible（最多 6、TxId 固定）→ 儲存版面後回列表確認
4. 點欄位 header：依設定預設方向啟動，再循環 Desc → 無 → Asc → Desc
5. `/page/system_setting` 仍為舊 maint
