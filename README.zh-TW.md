# Plurk Backup Viewer

[English](README.md) | 繁體中文

增強版的 Plurk 備份瀏覽器，支援全文搜尋功能。

## 功能特色

- **首頁** - 個人資料卡片與導覽列
- **全文搜尋** - 搜尋所有噗文與回應（FTS5 + LIKE 備援模式）
- **連結搜尋** - 透過 Open Graph 資料搜尋網址、標題與描述
- **彈出視窗** - 檢視噗文詳情與回應
- **增量匯入** - 新增備份資料時無需重建資料庫
- **網頁管理介面** - 透過瀏覽器上傳備份、建立資料庫、取得連結元資料

## 快速開始

### 方式 A：Docker（推薦）

不需要安裝 Python。內建網頁管理介面可上傳備份。

```bash
# 1. 複製並啟動
git clone https://github.com/user/plurk-backup-viewer
cd plurk-backup-viewer
docker compose up

# 2. 開啟管理介面
open http://localhost:8001

# 3. 上傳你的備份 .zip，然後點擊「Build Database」
# 4.（選用）取得連結元資料，讓分享的連結也能被搜尋
# 5. 搜尋功能在 http://localhost:8000 上線
```

### 方式 B：本地安裝

前置需求：Python 3.11+、[uv](https://github.com/astral-sh/uv)（Python 套件管理工具）

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
└── plurk-backup-viewer/       # 此專案
    ├── viewer/             # HTML 範本（靜態檔案）
    │   ├── landing.html    # 增強版首頁
    │   ├── search.html     # 搜尋介面
    │   └── admin.html      # 管理介面
    ├── data/               # 使用者資料（自動建立）
    │   ├── plurks.db       # 搜尋資料庫
    │   └── config.json     # 指向備份目錄
    └── tools/              # CLI 工具
```

## 指令說明

所有指令都在 `tools/` 目錄下執行。

### 建立資料庫

```bash
uv run plurk-tools init <backup_path>
```

建立：
- `data/plurks.db` - 包含所有噗文與回應的 SQLite 資料庫
- `data/config.json` - 指向備份目錄的設定檔

### 啟動伺服器

```bash
uv run plurk-tools serve [--port 8000]
```

啟動本地伺服器，同時提供增強版瀏覽器與你的備份資料。管理介面預設在 `http://localhost:8001`。使用 `--admin-port 0` 可停用。

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

## Docker 設定

Docker 設定會啟動一個容器，包含搜尋伺服器（連接埠 8000）和管理介面（連接埠 8001）。

```bash
# 建置並啟動
docker compose up

# 搭配 Cloudflare Tunnel（選用）
TUNNEL_TOKEN=your-token docker compose up
```

**掛載目錄：**
- `viewer/` 以唯讀方式掛載（靜態 HTML 範本）
- `data/` 以讀寫方式掛載（資料庫、設定檔、上傳的備份）

**連接埠：**
- `8000` - 搜尋介面（可透過 tunnel 對外）
- `8001` - 管理介面（僅限本地）

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

使用 Docker 時：透過管理介面重新上傳並重新初始化即可。

## 中日韓搜尋優化（選用）

預設的 FTS5 分詞器（`unicode61`）可以進行基本的中日韓搜尋，但如果需要更好的中文斷詞效果，可以安裝 [fts5-icu-tokenizer](https://github.com/cwt/fts5-icu-tokenizer) 擴充套件。

1. 從該專案編譯 `libfts5_icu.dylib`（macOS）或 `libfts5_icu.so`（Linux）
2. 放置到 `viewer/lib/` 目錄
3. 重建 FTS5 索引：

```bash
uv run plurk-tools reindex
```

`init` 和 `reindex` 都會從 `viewer/lib/` 自動偵測擴充套件。

| 分詞器 | 中日韓行為 |
|--------|-----------|
| `unicode61`（預設） | 逐字分詞，適用於大部分搜尋 |
| `icu`（需安裝擴充套件） | 正確的中文、日文、韓文斷詞 |

Docker 映像已內建 ICU 擴充套件。

## 運作原理

- **資料庫**：SQLite 搭配 FTS5 全文搜尋索引，儲存在 `data/`
- **雙目錄路由**：伺服器結合瀏覽器檔案與你的備份資料
- **最小修改**：只有 `patch` 指令會修改 `index.html`，其他備份檔案不會被修改
- **管理介面**：雙欄式網頁介面，上傳備份、建立資料庫、取得連結元資料

## 授權條款

MIT
