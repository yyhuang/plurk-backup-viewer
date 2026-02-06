# Plurk Backup Viewer

[English](README.md) | 繁體中文

增強版的 Plurk 備份瀏覽器，支援全文搜尋功能。

## 功能特色

- **首頁** - 個人資料卡片與導覽列
- **全文搜尋** - 搜尋所有噗文與回應（FTS5 + LIKE 備援模式）
- **連結搜尋** - 透過 Open Graph 資料搜尋網址、標題與描述
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

# 3. 初始化資料庫
uv run plurk-tools init ../username-backup

# 4. 啟動伺服器
uv run plurk-tools serve
# 開啟 http://localhost:8000

# 5.（選用）在原始 index.html 加入增強版瀏覽器連結
uv run plurk-tools patch
```

## 設定完成後的目錄結構

```
~/my-plurk/
├── username-backup/           # 你的 Plurk 匯出檔（不會被修改）
│   ├── index.html          # 原始 Plurk 瀏覽器
│   ├── static/
│   └── data/
│
└── plurk-backup-viewer/       # 此專案（保留用於啟動伺服器）
    ├── viewer/             # HTML + 資料庫
    │   ├── landing.html    # 增強版首頁
    │   ├── search.html     # 搜尋介面
    │   ├── plurks.db       # 搜尋資料庫
    │   └── config.json     # 指向備份目錄
    └── tools/              # CLI 工具
```

## 指令說明

所有指令都在 `tools/` 目錄下執行。

### 初始化資料庫

```bash
uv run plurk-tools init <backup_path>
```

建立：
- `viewer/plurks.db` - 包含所有噗文與回應的 SQLite 資料庫
- `viewer/config.json` - 指向備份目錄的設定檔

### 啟動伺服器

```bash
uv run plurk-tools serve [--port 8000]
```

啟動本地伺服器，同時提供增強版瀏覽器與你的備份資料。

### 修補原始瀏覽器（選用）

```bash
uv run plurk-tools patch
```

在原始 Plurk 備份的 `index.html` 加入「Enhanced Viewer」連結。每次解壓縮新備份後都需要重新執行。

### 連結元資料（選用）

從噗文中擷取網址並取得 Open Graph 元資料，以便搜尋連結：

```bash
# 擷取特定月份的連結
uv run plurk-tools links extract --month 201810

# 取得待處理連結的 OG 元資料
uv run plurk-tools links fetch --limit 100

# 檢查狀態
uv run plurk-tools links status
```

## 更新備份

當你從 Plurk 匯出新的備份時：

1. 解壓縮新備份（可以覆蓋舊的）
2. 再次執行 `plurk-tools init` - 會增量匯入新噗文
3. 再次執行 `plurk-tools patch` - 新解壓縮會覆蓋 `index.html`

```bash
# 重新執行 init 以匯入新資料
uv run plurk-tools init ../username-backup

# 重新執行 patch（新解壓縮會覆蓋 index.html）
uv run plurk-tools patch
```

## 運作原理

- **資料庫**：SQLite 搭配 FTS5 全文搜尋索引
- **雙目錄路由**：伺服器結合瀏覽器檔案與你的備份資料
- **最小修改**：只有 `patch` 指令會修改 `index.html`，其他備份檔案不會被修改

## 授權條款

MIT
