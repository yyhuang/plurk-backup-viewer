# Plurk Backup Viewer

[English](README.md) | 繁體中文

增強版的 Plurk 備份瀏覽器，支援全文搜尋、連結搜尋與中日韓文分詞。

**你的資料不會離開你的電腦。** 所有備份資料和搜尋資料庫都儲存在本地的 `data/` 目錄中，不會上傳到網路上——整個應用程式完全在你自己的電腦上運行。選用的 Cloudflare Tunnel 只會開放你選擇分享的搜尋介面。

## 前置需求

- [Docker](https://docs.docker.com/get-docker/)
- Windows 使用者：請參考 [Windows 安裝指南](WINDOWS-SETUP.zh-TW.md)，有逐步的 WSL2 + Docker 安裝說明

## 快速開始

```bash
git clone https://github.com/user/plurk-backup-viewer
cd plurk-backup-viewer
docker compose up
```

1. 開啟管理介面 http://localhost:8001
2. 上傳你的 Plurk 備份 `.zip` 檔案
3. 點擊 **Build Database**
4.（選用）點擊 **Fetch Link Metadata** 讓分享的連結也能被搜尋
5. 搜尋功能在 http://localhost:8000 上線

## 連接埠

| 連接埠 | 說明 |
|--------|------|
| `8000` | 搜尋介面 |
| `8001` | 管理介面（僅限本地） |

## 更新備份

從 Plurk 匯出新備份後，透過管理介面 http://localhost:8001 重新上傳並重建即可。

## 更新工具

拉取新版程式碼後，需重新建置 Docker 映像：

```bash
git pull
docker compose up --build
```

## Cloudflare Tunnel（選用）

透過 Cloudflare Tunnel 對外開放搜尋介面：

```bash
TUNNEL_TOKEN=your-token docker compose up
```

## 開發

本地安裝（不使用 Docker）、CLI 指令與專案架構，請參考 [DEVELOPMENT.zh-TW.md](DEVELOPMENT.zh-TW.md)。

## 授權條款

MIT
