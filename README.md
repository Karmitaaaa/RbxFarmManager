# RbxFarm Manager

A Windows desktop app that organizes Roblox farming: encrypted accounts, several Roblox clients at once,
anti-AFK, auto-reconnect, an autoclicker and macros organized per game. The interface is inspired by the
classic Roblox website (blue top bar, grey background, white cards, round avatars) and has a dark theme.

> **Note:** the app's interface is currently in Spanish.

> RbxFarm Manager only uses external automation (Windows windows, keyboard and mouse). It does not inject
> code and never reads or modifies the Roblox client's memory. Even so, automation and alternate accounts
> may go against the Roblox Terms of Use or a game's rules: use it at your own risk.

---

## Install

1. Go to **[Releases](https://github.com/Karmitaaaa/RbxFarmManager/releases/latest)** and download one of:
   - **`RbxFarmManager-WebSetup.exe`** (~2 MB): downloads the latest version from GitHub and installs it.
   - **`RbxFarmManager-Setup.exe`** (~120 MB): full offline installer.
2. Run it and follow the steps. It installs for your user only (no administrator rights needed) and adds a
   Start menu shortcut (and a desktop shortcut if you tick it).
3. Open **RbxFarm Manager** and sign in with your Roblox account.

**Updates:** the app checks GitHub when it starts and every 6 hours. When a new version is out, a banner
appears: click **«Actualizar ahora»** (Update now) and the app downloads it, verifies its SHA-256, installs
it and reopens by itself. Your accounts, games and macros are kept. You can also check manually in
**Registro → Actualizaciones** (Log → Updates) or turn the check off there.

To uninstall, use Windows «Add or remove programs» (your data in `%APPDATA%\RbxFarmManager` is kept).

> The installers are not digitally signed, so Windows SmartScreen may say «Windows protected your PC».
> Click **More info → Run anyway**.

## Features

- **Sign in with Roblox:** the official Roblox login page opens inside the app; you type your password on
  roblox.com and RbxFarm never sees it. Sessions are stored encrypted on your PC (Windows DPAPI, or an
  optional master password).
- **Game profiles:** pick a game (or private server), which accounts join and which macro or autoclicker
  preset they use, then press **Play**. The real game name and icon are fetched from Roblox.
- **Multi-instance:** several Roblox clients at once, with status (launching, open, in game, reconnecting…),
  CPU/RAM, FPS cap, low CPU priority and auto-minimize.
- **Anti-AFK** with randomized intervals, **auto-reconnect** with exponential back-off (detects crashes,
  error dialogs, server disconnections and internet loss), **autoclicker** and **macro recorder/player**
  with global hotkeys.
- Greeting with your main account's name and avatar, first-steps guide, tray icon and notifications.

---

## Build from source

Requirements: Windows 10/11, Python 3.11+ (tested with 3.14) and Roblox Player (Bloxstrap and Fishstrap
also work). To build the installers you also need [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`).

Run from source:

```bat
cd RbxFarmManager
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

> If the folder path is very long, Windows may fail to load `cryptography` ("file name or extension is too
> long"). Move the project to a short path such as `C:\RbxFarmManager`.

Build the app and both installers:

```bat
build.bat
```

The script creates the virtual environment, installs dependencies, generates the icon and runs PyInstaller.
Output goes to a `Build` folder next to the project folder:

- `..\Build\RbxFarmManager\RbxFarmManager.exe` — the app
- `..\Build\Instalador\RbxFarmManager-Setup.exe` — full installer (version taken from `VERSION`)
- `..\Build\Instalador\RbxFarmManager-WebSetup.exe` — web installer

### Releasing a new version

1. Bump the number in `VERSION` (e.g. `1.2.0`) and run `build.bat`.
2. Create a GitHub Release whose tag is that version and attach **both** installers with these exact names
   (the web installer and the in-app updater look for `RbxFarmManager-Setup.exe` in the latest Release):

```bat
gh release create v1.2.0 ..\Build\Instalador\RbxFarmManager-Setup.exe ..\Build\Instalador\RbxFarmManager-WebSetup.exe --title "RbxFarm Manager 1.2.0" --notes "What's new…"
```

Installed copies will see the new version within 6 hours (or right away when they start).

---

## Project structure

```
RbxFarmManager/
├─ main.py                  Entry point: logging, theme, vault, welcome screen, main window
├─ VERSION                  App version (bundled into the .exe, used by the updater and installers)
├─ build.bat                Builds the app (PyInstaller) and the installers (Inno Setup)
├─ installer/               RbxFarmManager.iss (full installer) and RbxFarmManager-WebSetup.iss
├─ tools/make_icon.py       Generates assets/icon.ico
├─ core/                    Logic (no UI)
│  ├─ models.py             Account, Instance, GameProfile, LaunchTarget and states
│  ├─ roblox_api.py         Auth ticket, session check, share links, game info, avatars and icons
│  ├─ launcher.py           Launch URIs, multi-instance mutex, FPS cap, client log matching
│  ├─ instance_manager.py   Launch queue + status monitor + auto-reconnect
│  ├─ reconnect.py          Back-off, disconnection detection, internet check
│  ├─ updater.py            GitHub Releases update check, download and install
│  ├─ anti_afk.py           Anti-AFK
│  ├─ autoclicker.py        Autoclicker
│  ├─ macro.py              Macro recorder and player
│  └─ timing.py             1 ms timer resolution for accurate timing
├─ storage/
│  ├─ crypto.py             Fernet + scrypt, or Windows DPAPI
│  ├─ vault.py              Encrypted account vault (import/export)
│  ├─ config.py             JSON settings with autosave
│  ├─ games.py              Game profiles (games.json)
│  └─ profiles.py           Macro profiles (one JSON per macro, with its game)
├─ ui/
│  ├─ theme.py              Classic-style stylesheet (light and dark)
│  ├─ icons.py              Windows vector icons (Segoe Fluent Icons / MDL2)
│  ├─ widgets.py            Game cards, avatars, headers, empty states, notifications
│  ├─ avatars.py            Avatar photo and game icon cache
│  ├─ dialogs.py            Welcome, unlock, account editor, passwords
│  ├─ roblox_login.py       Sign in with the official Roblox page (embedded browser)
│  ├─ game_dialog.py        Game profile editor
│  ├─ updates.py            Update banner and update dialog
│  ├─ main_window.py        Top bar, sidebar, tray, hotkeys
│  └─ tabs/                 Home, Games, Instances, Anti-AFK, Autoclicker, Macros, Log
└─ utils/
   ├─ winapi.py             SendInput, windows and focus (public Windows APIs)
   ├─ hotkeys.py            Global hotkeys (pynput)
   ├─ logger.py             Rotating file log; hides cookies and tickets
   ├─ version.py            App version and version comparison
   └─ paths.py              Data paths
```

Data lives in `%APPDATA%\RbxFarmManager`: `vault.dat` (encrypted accounts), `games.json`,
`settings.json`, `macros\*.json`, `avatars\` and `logs\rbxfarm.log`.

---

## How it works (technical notes)

- **Sign-in:** the embedded browser uses a fresh temporary profile for each sign-in, so several accounts
  can be added one after another. When Roblox sets the `.ROBLOSECURITY` session cookie, the app reads it,
  checks with roblox.com which account it belongs to and stores it encrypted. The session is only ever
  sent to roblox.com (to request a one-time launch ticket). Cookies and tickets are never written to logs.
- **Multi-instance:** the app holds Roblox's single-instance mutex before launching, so each new client
  opens without closing the others. Accounts are launched one at a time so each process is matched to its
  account. If Roblox was already open before the app, close it and launch again.
- **In game / disconnected** status is read from the text log Roblox writes to
  `%LOCALAPPDATA%\Roblox\logs`. If Roblox changes its log format, update `JOIN_MARKERS` and
  `DISCONNECT_MARKERS` in `core/reconnect.py`.
- **Shared real input:** anti-AFK, macros and the autoclicker use the system keyboard and mouse, so a global
  lock makes them take turns; a looping macro releases it between loops so other accounts' anti-AFK can run.
- **FPS cap** is written to Roblox's `ClientAppSettings.json` and applies to clients launched afterwards.
  Bloxstrap/Fishstrap manage their own settings, so set it there as well.
- **Updates:** the updater reads `releases/latest` from the GitHub API, downloads `RbxFarmManager-Setup.exe`,
  checks its SHA-256 against the digest GitHub publishes, then runs it with
  `/SILENT /CLOSEAPPLICATIONS /RELAUNCH=1`. The installer waits for the app to close, updates it and
  reopens it.
