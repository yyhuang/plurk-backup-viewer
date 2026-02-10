# Windows 安裝指南

[English](WINDOWS-SETUP.md) | 繁體中文

這份指南會帶你在 Windows 上安裝 Docker，讓你可以執行 Plurk Backup Viewer。不需要任何命令列使用經驗。

## 系統需求

- Windows 10 2004 版或更新版本，或 Windows 11
- 至少 4 GB 記憶體（建議 8 GB）
- 電腦的系統管理員權限

## 步驟一：啟用 WSL2

WSL2（Windows Subsystem for Linux）讓 Windows 可以執行 Linux 工具。Docker Desktop 需要它才能運作。

1. 點擊左下角的**開始**按鈕（Windows 圖示）
2. 輸入 **PowerShell**
3. 在 **Windows PowerShell** 上按右鍵，選擇**以系統管理員身分執行**
4. 如果出現「你要允許此 App 變更你的裝置嗎？」的對話框，點擊**是**
5. 會出現一個藍色/黑色的視窗。複製貼上以下指令，然後按 **Enter**：

   ```
   wsl --install
   ```

6. 等待安裝完成。你會看到下載和安裝 Ubuntu 的訊息
7. 出現提示時，**重新啟動電腦**

重新啟動後，可能會彈出一個視窗要求你建立 Linux 的使用者名稱和密碼。你可以隨意設定（這只用於 Linux，不會影響你的 Windows 帳號）。如果這個視窗沒有出現也沒關係。

### 確認 WSL2 正常運作

1. 再次開啟 **PowerShell**（這次不需要系統管理員）
2. 輸入以下指令並按 **Enter**：

   ```
   wsl --status
   ```

3. 你應該會看到一行寫著 **Default Version: 2**。如果顯示 version 1，請執行：

   ```
   wsl --set-default-version 2
   ```

## 步驟二：安裝 Docker Desktop

1. 開啟瀏覽器，前往：https://www.docker.com/products/docker-desktop/
2. 點擊 **Download for Windows** 按鈕
3. 開啟下載的檔案（`Docker Desktop Installer.exe`）
4. 如果出現「你要允許此 App 變更你的裝置嗎？」的對話框，點擊**是**
5. 在安裝程式中，確認 **Use WSL 2 instead of Hyper-V** 選項已勾選（預設應該已勾選）
6. 點擊 **Ok**，等待安裝完成
7. 點擊 **Close and restart**（電腦會重新啟動）

### 啟動 Docker Desktop

1. 重新啟動後，Docker Desktop 可能會自動啟動。如果沒有，點擊**開始**按鈕，輸入 **Docker Desktop** 並開啟它
2. 可能會出現授權條款 — 點擊 **Accept** 繼續
3. 可以跳過或關閉任何歡迎頁面或教學
4. 等待 Docker Desktop 左下角顯示 **Engine running**（綠色圖示），這可能需要一兩分鐘

> 如果看到關於 WSL2 的警告，請回到步驟一確認 WSL2 已正確安裝。

### 確認 Docker 正常運作

1. 開啟 **PowerShell**
2. 輸入以下指令並按 **Enter**：

   ```
   docker --version
   ```

3. 你應該會看到類似 `Docker version 27.x.x` 的文字 — 確切版本號碼不重要

## 步驟三：執行 Plurk Backup Viewer

現在你可以照著 [README](README.zh-TW.md) 的說明操作了。以下是 Windows 上的具體步驟：

1. 選擇一個要放置專案的資料夾。例如桌面或文件資料夾

2. 開啟 **PowerShell**，切換到該資料夾。例如切換到桌面：

   ```
   cd ~/Desktop
   ```

3. 下載專案：

   ```
   git clone https://github.com/user/plurk-backup-viewer
   ```

   > 如果看到 `git` 無法辨識的錯誤，你可以改用 ZIP 方式下載：
   > 前往 GitHub 頁面，點擊綠色的 **Code** 按鈕，然後選擇 **Download ZIP**。
   > 將 ZIP 解壓縮到桌面，並將資料夾重新命名為 `plurk-backup-viewer`。

4. 進入專案資料夾：

   ```
   cd plurk-backup-viewer
   ```

5. 啟動應用程式：

   ```
   docker compose up
   ```

   第一次執行時，Docker 會下載並建置所有東西。這可能需要幾分鐘。你會看到很多文字不斷滾動 — 這是正常的。

6. 當你看到類似 `Serving on port 8000` 的訊息，表示應用程式已經準備好了

7. 開啟瀏覽器，前往：
   - **管理介面**：http://localhost:8001（在這裡上傳你的備份）
   - **搜尋介面**：http://localhost:8000（在這裡搜尋你的噗文）

### 停止應用程式

回到 PowerShell 視窗，按下 **Ctrl + C** 即可停止。

### 之後再次啟動

不需要重新安裝。只要：

1. 確認 Docker Desktop 正在執行（查看時鐘旁邊系統匣的鯨魚圖示）
2. 開啟 **PowerShell**
3. 進入專案資料夾並啟動：

   ```
   cd ~/Desktop/plurk-backup-viewer
   docker compose up
   ```

## 常見問題

### 出現「Docker Desktop - WSL2 based engine」錯誤

確認 WSL2 已安裝。以系統管理員身分開啟 PowerShell 並執行：

```
wsl --install
```

然後重新啟動電腦。

### Docker Desktop 無法啟動

- 確認 BIOS/UEFI 中已啟用虛擬化。通常在 CPU 設定中，標示為「Intel VT-x」或「AMD-V」。確切步驟因電腦品牌而異 — 搜尋「[你的電腦品牌] 啟用虛擬化」
- 嘗試重新啟動電腦

### 「docker compose」無法辨識

- 確認 Docker Desktop 正在執行（查看時鐘旁邊系統匣的鯨魚圖示）
- 嘗試關閉並重新開啟 PowerShell

### 下載/建置非常慢

第一次執行會下載大量資料，這是正常的。之後再次執行會快很多，因為 Docker 會快取所有東西。

### 連接埠已被使用

如果看到關於 port 8000 或 8001 的錯誤，表示其他應用程式正在使用該連接埠。關閉該應用程式，或稍等一下再試。
