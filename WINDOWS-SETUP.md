# Windows Setup Guide

English | [繁體中文](WINDOWS-SETUP.zh-TW.md)

This guide walks you through setting up Docker on Windows so you can run Plurk Backup Viewer. No prior experience with command line is needed.

## Requirements

- Windows 10 version 2004 or later, or Windows 11
- At least 4 GB of RAM (8 GB recommended)
- Administrator access to your computer

## Step 1: Enable WSL2

WSL2 (Windows Subsystem for Linux) lets Windows run Linux tools. Docker Desktop needs it.

1. Click the **Start** button (Windows icon at the bottom-left corner)
2. Type **PowerShell**
3. Right-click **Windows PowerShell** and choose **Run as administrator**
4. If a dialog asks "Do you want to allow this app to make changes to your device?", click **Yes**
5. A blue/black window will appear. Copy and paste this command, then press **Enter**:

   ```
   wsl --install
   ```

6. Wait for it to finish. You will see messages about downloading and installing Ubuntu
7. **Restart your computer** when prompted

After restarting, a window may pop up asking you to create a Linux username and password. You can set these to anything you like (they are only for Linux and do not affect your Windows account). If this window does not appear, that is fine too.

### Verify WSL2 is working

1. Open **PowerShell** again (no need for administrator this time)
2. Type this command and press **Enter**:

   ```
   wsl --status
   ```

3. You should see a line that says **Default Version: 2**. If it says version 1 instead, run:

   ```
   wsl --set-default-version 2
   ```

## Step 2: Install Docker Desktop

1. Open your web browser and go to: https://www.docker.com/products/docker-desktop/
2. Click the **Download for Windows** button
3. Open the downloaded file (`Docker Desktop Installer.exe`)
4. If a dialog asks "Do you want to allow this app to make changes to your device?", click **Yes**
5. In the installer, make sure **Use WSL 2 instead of Hyper-V** is checked (it should be checked by default)
6. Click **Ok** and wait for installation to finish
7. Click **Close and restart** (your computer will restart)

### Start Docker Desktop

1. After restarting, Docker Desktop may start automatically. If not, click the **Start** button, type **Docker Desktop**, and open it
2. You may see a license agreement — click **Accept** to continue
3. You can skip or close any welcome surveys or tutorials
4. Wait until Docker Desktop shows **Engine running** (green icon) in the bottom-left corner. This may take a minute or two

> If you see a warning about WSL2, go back to Step 1 and make sure WSL2 is installed correctly.

### Verify Docker is working

1. Open **PowerShell**
2. Type this command and press **Enter**:

   ```
   docker --version
   ```

3. You should see something like `Docker version 27.x.x` — the exact number does not matter

## Step 3: Run Plurk Backup Viewer

Now you can follow the main [README](README.md) instructions. Here are the Windows-specific steps:

1. Choose a folder where you want to put the project. For example, your Documents folder

2. Open **PowerShell** and navigate to that folder:

   ```
   cd ~/Documents
   ```

3. Download the project:

   ```
   git clone https://github.com/user/plurk-backup-viewer
   ```

   > If you see an error that `git` is not recognized, you can download the project as a ZIP file instead:
   > go to the GitHub page, click the green **Code** button, then **Download ZIP**.
   > Extract the ZIP to your Documents folder and rename the folder to `plurk-backup-viewer`.

4. Go into the project folder:

   ```
   cd plurk-backup-viewer
   ```

5. Start the application:

   ```
   docker compose up
   ```

   The first time you run this, Docker will download and build everything. This may take several minutes. You will see a lot of text scrolling — this is normal.

6. When you see a message like `Serving on port 8000`, the application is ready

7. Open your web browser and go to:
   - **Admin interface**: http://localhost:8001 (upload your backup here)
   - **Search interface**: http://localhost:8000 (search your plurks here)

### Stopping the application

To stop the application, go back to the PowerShell window and press **Ctrl + C**.

### Starting again later

You do not need to repeat the setup. Just:

1. Make sure Docker Desktop is running (check the system tray icon near the clock)
2. Open **PowerShell**
3. Go to the project folder and start it:

   ```
   cd ~/Documents/plurk-backup-viewer
   docker compose up
   ```

## Troubleshooting

### "Docker Desktop - WSL2 based engine" error

Make sure WSL2 is installed. Open PowerShell as administrator and run:

```
wsl --install
```

Then restart your computer.

### Docker Desktop does not start

- Make sure virtualization is enabled in your BIOS/UEFI. This is usually under CPU settings, labeled "Intel VT-x" or "AMD-V". The exact steps depend on your computer manufacturer — search for "[your computer brand] enable virtualization"
- Try restarting your computer

### "docker compose" is not recognized

- Make sure Docker Desktop is running (look for the whale icon in the system tray near the clock)
- Try closing and reopening PowerShell

### The download/build is very slow

The first run downloads a lot of data. This is normal. Subsequent runs will be much faster because Docker caches everything.

### Port already in use

If you see an error about port 8000 or 8001, another application is using that port. Close the other application, or wait a moment and try again.
