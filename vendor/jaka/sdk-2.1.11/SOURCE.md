# JAKA Python SDK 2.1.11（Windows x64）部署來源說明

本目錄供 RoboArm 以專案內路徑載入 JAKA Python SDK，避免執行期依賴 ZiYan 臨時目錄。

## 來源套件

| 項目 | 值 |
|------|-----|
| 來源根目錄 | `U:\Ben\ZiYan\Documents\jaka\jakaAPI_V2.1.11\` |
| 執行檔來源 | `...\SDK2.1.11\Windows\python3\x64\` |
| 套件標籤（資料夾／說明文件） | **2.1.11**（`jakaAPI_V2.1.11`、`SDK2.1.11`、`readme_EN.txt`、`changelog` 之 V2.1.11 區段） |
| `jakaAPI.dll` 內嵌 FileVersion / ProductVersion | **未提供**（VersionInfo 為空／`0.0.0.0`） |
| 授權檔 | 來源套件中**未發現**獨立 LICENSE／COPYING 檔 |

## 本機部署路徑

- SDK 執行目錄：`vendor/jaka/sdk-2.1.11/windows-x64/`（相對專案根目錄）
- 版本說明副本：`readme_EN.txt`、`readme_CN.txt`、`changelog`（本層）
- 雜湊清單：`FILE_MANIFEST.json`

## 重建步驟

1. 僅自來源 `Windows\python3\x64\` 複製同套件檔案（勿混入 2.1.7、x86、其他語言目錄）。
2. 以 `FILE_MANIFEST.json` 比對大小與 SHA-256。
3. 使用已確認的 Python 3.10.11（64-bit）候選環境，將 SDK 目錄加入 `PATH`／`os.add_dll_directory` 與 `sys.path` 後 `import jkrc`；確認 `__file__` 落在本專案 `vendor\jaka\...`，且路徑不含 ZiYan。
4. 勿建立控制器、勿連實機。

## Git 政策

- `windows-x64` 下之 `.dll`／`.pyd`／`.lib`／`.exp` 預設由 `.gitignore` 排除，**未確認授權與第三方二進位管理規則前不得加入 Git 暫存**。
- 本說明、`FILE_MANIFEST.json` 與 readme／changelog 可納入版本庫以便重建部署。
