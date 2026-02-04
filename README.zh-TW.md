# Plurk Backup Viewer

[English](README.md) | 繁體中文

增強版的 Plurk 備份瀏覽器，支援全文搜尋功能。

## 功能特色

- **首頁** - 個人資料卡片與導覽列
- **全文搜尋** - 搜尋所有噗文與回應（FTS5 + LIKE 備援模式）
- **連結搜尋** - 透過 Open Graph 資料搜尋連結標題與描述
- **彈出視窗** - 檢視噗文詳情與回應
- **增量匯入** - 新增備份資料時無需重建資料庫

## 前置需求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（Python 套件管理工具）

## 快速開始

```bash
# 1. 解壓縮你的 Plurk 備份
cd ~/my-plurk
unzip your-backup.zip
# 這會建立一個目錄，例如：username-backup/

# 2. 複製此專案
git clone https://github.com/user/plurk-backup-viewer
cd plurk-backup-viewer/tools
uv sync

# 3. 初始化瀏覽器（會建立平行目錄）
uv run plurk-tools init ../username-backup
# 輸出：Created viewer at ~/my-plurk/username-viewer/
#       Database: X plurks, Y responses

# 4. 啟動伺服器
uv run plurk-tools serve ../username-viewer
# 開啟 http://localhost:8000
```

## 設定完成後的目錄結構

```
~/my-plurk/
├── username-backup/           # 你的 Plurk 匯出檔（不會被修改）
│   ├── index.html          # 原始 Plurk 瀏覽器
│   ├── static/
│   └── data/
│
├── username-viewer/           # 由 plurk-tools init 建立
│   ├── landing.html        # 增強版首頁
│   ├── search.html         # 搜尋介面
│   ├── static/sql-wasm.*   # 瀏覽器用 SQLite
│   ├── plurks.db           # 搜尋資料庫
│   └── config.json         # 指向備份目錄的設定檔
│
└── plurk-backup-viewer/    # 此專案（設定完成後可刪除）
```

## 指令說明

所有指令都在 `tools/` 目錄下執行。

### 初始化瀏覽器

```bash
uv run plurk-tools init <backup_path> [--viewer <viewer_path>]
```

建立瀏覽器目錄，包含：
- 增強版檢視用的 HTML 模板
- 包含所有噗文與回應的 SQLite 資料庫
- 指向備份目錄的設定檔

預設瀏覽器路徑：`<backup_name>-viewer`（與備份目錄平行）

### 啟動伺服器

```bash
uv run plurk-tools serve <viewer_path> [--port 8000]
```

啟動本地伺服器，同時提供增強版瀏覽器與你的備份資料。

### 連結元資料（選用）

從噗文中擷取網址並取得 Open Graph 元資料，以便搜尋連結：

```bash
# 擷取特定月份的連結
uv run plurk-tools links extract <viewer_path> --month 201810

# 取得待處理連結的 OG 元資料
uv run plurk-tools links fetch <viewer_path> --limit 100

# 檢查狀態
uv run plurk-tools links status <viewer_path>
```

## 更新備份

當你從 Plurk 匯出新的備份時：

1. 解壓縮新備份（可以覆蓋舊的）
2. 再次執行 `plurk-tools init` - 會增量匯入新噗文

```bash
# 重新執行 init 以匯入新資料
uv run plurk-tools init ../username-backup
# 輸出：Added X new plurks, Y new responses
```

## 運作原理

- **資料庫**：SQLite 搭配 FTS5 全文搜尋索引
- **雙目錄路由**：伺服器結合瀏覽器檔案與你的備份資料
- **不修改原檔**：你的原始備份檔案永遠不會被修改

## 授權條款

MIT
