# JAKA SDK 2.1.11 — 控制器 IP 搜尋介面調查

調查／probe 記錄日期：2026-10-28  
適用套件：`jakaAPI_V2.1.11` / `SDK2.1.11`（專案部署：`vendor/jaka/sdk-2.1.11/windows-x64`）

性質：文件／標頭／符號檢查，以及一次使用者手動觸發的
控制器搜尋驗證。

曾呼叫模組級 jkrc.get_controller_ip()；
未建立 RC、未登入控制器。

最近一次文件更新僅補充錯誤碼依據，未再次執行搜尋。

調查階段（勿混淆）：

1. **文件／離線階段**（搜尋前）：僅讀標頭、手冊、符號；該階段未呼叫搜尋。  
2. **手動 probe 階段**（約 2026-10-28 17:28）：使用者執行真實 `--run-search` 一次；結果見 §3。  
3. **後續僅改文件**：補充 `-3`／`ERR_COMMUNICATION_ERR` 等依據；**未**再執行搜尋。

整份文件總述**不得**再宣稱「從未執行搜尋」。

## 1. 結論

**已確認支援**控制器 IP 查詢介面：`get_controller_ip`。

**已用真實 probe 驗證**（見 §3）：模組級 `jkrc.get_controller_ip()` **可無參數呼叫**，且**不建立 `RC`、不登入**即可完成該呼叫。

**重要區分：** 外層工具／worker 回傳 `ok=true`（呼叫完成並記錄到原始回傳）**不代表** SDK 搜尋成功。本次 SDK 第一個元素為非零 `-3`，屬 SDK 錯誤碼路徑，**不得**解讀為「沒有設備」，**不得**據此修改任何 verified 狀態。

本介面用途為查詢控制器 IP，**不是**「以已知 IP 登入」；「測試指定 IP 連線」屬另一操作。

---

## 2. 介面依據（SDK 2.1.11 文件／標頭）

> 本節主要來自**文件／離線階段**的標頭與手冊核對；其中「未呼叫」僅指該階段，不否定之後的手動 probe。

### 2.1 C API（無 handle，獨立函式）

- 檔案：`U:\Ben\ZiYan\Documents\jaka\jakaAPI_V2.1.11\SDK2.1.11\Windows\c&c++\inc_of_c\jakaAPI.h`（約 685–690 行）

```c
/**
* @brief 获取控制器IP
* @param controller_name 控制器名字
* @param ip_list 控制器ip列表，控制器名字为具体值时返回该名字所对应的控制器IP地址，控制器名字为空时，返回网段类内的所有控制器IP地址
* @return ERR_SUCC 成功 其他失败
*/
DLLEXPORT_API errno_t get_controller_ip(char *controller_name, char *ip_list);
```

### 2.2 C++／C#

- C++：`JAKAZuRobot.h` — `JAKAZuRobot()`；`login_in(ip)`；`get_controller_ip(...)`（約 597–603 行）
- C#：`jakaAPI.cs` — 靜態 `get_controller_ip`（約 12–16 行），無 handler

### 2.3 Python 手冊

- 《Python SDK Manual V2.1.11》**§4.1.10 Get the controller IP**（約 p.11）
- Success：`(0, ip_list)`；Failure：Others；Parameter 欄空白；無 Sample Code
- 通則：Get 類回傳 `(errcode, data)`，成功時 `errcode == 0`

### 2.4 錯誤碼 `-3`（同套 SDK 原文）

| 來源 | 原文 |
|------|------|
| `...\Windows\c&c++\inc_of_c\jkerr.h` **第 8 行** | `#define ERR_COMMUNICATION_ERR	 -3             //fail to connect` |
| 同套件 `...\inc_of_c++\jkerr.h` **第 8 行** | 同上 |
| 《Python SDK Manual V2.1.11》錯誤碼表 | `ERR_COMMUNICATION_ERR -3 There was a communication error` |

宏名：**`ERR_COMMUNICATION_ERR`**。  
標頭註解原文：`fail to connect`。  
Python 手冊原文：`There was a communication error`。

**不把 `-3` 轉成「沒有設備」。** 本次僅記錄為 SDK 非零回傳碼 `-3`（`ERR_COMMUNICATION_ERR`）。該碼在 `get_controller_ip` 場景下的精確觸發條件（例如無裝置／網段不可達／其他）——**未由本 probe 單獨證明**。

---

## 3. 真實 probe 結果（與文件分開記錄）

時間：約 **2026-10-28 17:28**（使用者手動觸發，單次）。  
工具：`tools/jaka_probe_controller_ip.py --run-search`（經既有 worker 通道）。  
約束：僅 `jkrc.get_controller_ip()`；無 RC、無登入、無改設備／verified。

### 3.1 已驗證的呼叫方式

1. 模組級 **`jkrc.get_controller_ip()` 可無參數呼叫**（未出現 `TypeError`）。
2. **不建立 `RC`、不登入**也能完成該呼叫。
3. 經專案 vendor 內 `jkrc` 載入即可（與 ZiYan 路徑無關之部署路徑）。

### 3.2 本次觀察結果（單次，非普適結論）

| 項目 | 觀察 |
|------|------|
| 呼叫耗時 | 約 **4.87 秒** |
| 回傳型別 | **`tuple`**：`(int, str)` |
| 回傳值 | **`(-3,` 含大量空字元的字串`)`** |
| 外層工具 | 呼叫完成並記錄原始回傳（工具層成功） |
| SDK 搜尋是否成功 | **否**（第一元素非 0）；見 §2.4 對 `-3` 的原文含義 |
| 是否解讀為「無設備」 | **否**（禁止） |
| 是否改 verified／存 IP | **否** |

### 3.3 尚未驗證

1. **成功回傳格式**：手冊寫 `(0, ip_list)`，但 `ip_list` 在 Python 實際為 `list` 還是 `str`（或其他）——**尚未在成功案例中驗證**。
2. **多 IP 分隔**：成功且多台時如何分隔／結構化——**未驗證**。
3. **空結果語意**：搜尋完成但無控制器時，是 `(0, "")`／`(0, [])`／其他非零碼——**未驗證**；本次 `-3` **不得**當作該語意的證明。
4. 具名 `controller_name` 參數的 Python 寫法與行為——**未在本 probe 驗證**（本輪刻意只測無參數）。
5. `jkrc.RC.get_controller_ip` 與模組級是否等同——**未驗證**。
6. SDK 是否另有內建逾時、多網卡／防火牆細節——**未驗證**。

### 明確排除的推測

- 不推測底層 broadcast／UDP／特定 port／自掃網段。  
- 不因 `-3` 或空白字串推測「網段內沒有設備」。

---

## 4. 與「測試指定 IP」的區分

| | A. 搜尋控制器 | B. 測試指定 IP 連線 |
|--|----------------|---------------------|
| 目的 | 未知 IP 時找出候選 | 驗證已知 IP 可否連接 |
| 設定依賴 | **不得**要求 `HostAddress` 為必填 | 使用已知／暫存 IP |
| SDK | `get_controller_ip` | 另案（如 `RC(ip)` + `login`） |
| 成功後 | 僅供選取填入；不自動登入／不改 verified | 不自動標已連線 |

---

## 5. 接入方案備註（實作狀態）

- 手動 probe 工具已存在：`tools/jaka_probe_controller_ip.py`（預設不搜尋；`--run-search` 才真實呼叫）。
- Worker op：`probe_get_controller_ip`（僅無參數呼叫）。
- 正式 UI／公開 API／自動搜尋：**尚未做**（本輪不新增）。
- 後續正式搜尋接入時應：
  - 分開「呼叫完成」與「SDK errcode == 0」；
  - 非零碼（含 `-3`／`ERR_COMMUNICATION_ERR`）走錯誤／未成功路徑，並附原始碼與原文標籤；
  - **不**映射為「沒有設備」，除非另有成功案例證明空結果語意。

---

## 6. 本文件變更

- 開頭性質描述已與手動搜尋事實對齊：曾呼叫模組級 `get_controller_ip()`；未建 RC、未登入。  
- 分清「文件／離線階段未呼叫」與「其後一次手動真實搜尋」。  
- 保留 §3 之 `-3`／`ERR_COMMUNICATION_ERR`、約 4.87 秒，以及成功格式／多 IP／空結果尚未驗證說明。  
- 最近一次文件更新僅修正性質描述／階段標示（或僅補錯誤碼依據），**未再次執行搜尋**；未改程式、配置或 verified。
