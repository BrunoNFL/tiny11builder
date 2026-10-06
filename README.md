# tiny11builder
*Scripts to build a trimmed-down, bloatware-free Windows 11 image — natively on **macOS**, **Linux**, and **Windows**!*

Fork repository: **[BrunoNFL/tiny11builder](https://github.com/BrunoNFL/tiny11builder)**  
Upstream repository: **[ntdevlabs/tiny11builder](https://github.com/ntdevlabs/tiny11builder)**

---

## Overview

Tiny11 builder automates the creation of a streamlined, debloated Windows 11 installation media. It bypasses Microsoft's artificial hardware restrictions (TPM 2.0, Secure Boot, RAM, CPU checks, and storage requirements), removes telemetry, sponsored apps, and bloatware, and allows offline local account creation without forcing a Microsoft Account.

### Key Capabilities of this Fork:
- 🍏 **Native macOS & Linux Support**: Remaster official Windows 11 ARM64 and x64 ISOs directly on macOS (Apple Silicon or Intel) or Linux without needing a Windows PC or virtual machine!
- ⚡ **Zero Windows Servicing Binaries on Mac**: Uses `wimlib-imagex` for WIM modifications, `libhivex` for offline registry hives, and `xorriso` for hybrid UEFI/BIOS bootable ISO generation.
- 👤 **Flexible User Setup**:
  - **Standard Mode (Default)**: Normal interactive setup where you create your own username and password during OOBE, with network requirement checks bypassed.
  - **Unattended Mode (`--skip-user-creation`)**: Automatically creates an offline local administrator account and logs directly into the desktop.
- 🖥️ **Virtual Machine Ready**: Optimized for Apple Silicon virtualization tools such as **UTM**, **VMware Fusion**, and **Parallels Desktop**.

---

## 🛠️ Script Versions

| Script | Platform | Description |
| :--- | :--- | :--- |
| **`tiny11maker.sh`** | **macOS / Linux** | Native Bash script with Python registry modifier (`hivex`), `wimlib`, and `xorriso`. Supports interactive SKU selection, fast LZX compression, and optional unattended user creation. |
| **`tiny11maker.ps1`** | **Windows** | The original PowerShell script for Windows. Removes bloat while preserving servicing components. |
| **`tiny11coremaker.ps1`** | **Windows** | Minimalist build for quick testing environments. Significantly smaller, but removes servicing/WinSxS. |

---

## 🚀 Instructions: macOS & Linux

### 1. Prerequisites Installation

Install the required tools via [Homebrew](https://brew.sh/) on macOS:
```bash
brew install wimlib hivex xorriso
```
*(On Debian/Ubuntu Linux: `sudo apt install wimtools libhivex-bin xorriso python3`)*

Verify your setup:
```bash
./tiny11maker.sh --check-deps
```

### 2. Download Windows 11 ISO
Download an official Windows 11 ISO (x64 or ARM64) from the [Microsoft Download Page](https://www.microsoft.com/software-download/windows11) or [UUP dump](https://uupdump.net/).

### 3. Build Your Tiny11 ISO

#### Standard Interactive Setup (Default):
Lets you choose your own username and password during initial Windows setup:
```bash
./tiny11maker.sh -i /path/to/Windows11.iso
```

#### Unattended Setup (Skip User Creation & Boot Directly to Desktop):
Automatically pre-creates a local administrator account and enables auto-logon:
```bash
# Auto-creates user "Tiny11" and auto-logins to desktop
./tiny11maker.sh -i /path/to/Windows11.iso --skip-user-creation

# Or specify a custom account name:
./tiny11maker.sh -i /path/to/Windows11.iso --skip-user-creation "MyUser"
```

#### Fast Export Mode:
Use `--fast` to employ LZX compression instead of recovery LZMS (builds in ~1 minute instead of ~5 minutes):
```bash
./tiny11maker.sh -i /path/to/Windows11.iso --fast -o ./tiny11_custom.iso
```

### 4. CLI Options Reference

```text
Usage: ./tiny11maker.sh [options]

Options:
  -i, --iso <path>             Path to the Windows 11 ISO file
  -s, --scratch <dir>          Scratch workspace directory (default: ./scratch_tiny11)
  -o, --output <path>          Output ISO file path (default: ./tiny11.iso)
  -n, --index <number>         Windows image SKU index to export (e.g. 1, 2, 3)
  -w, --wimlib <path>          Custom path to wimlib-imagex executable
  -u, --username <name>        Create local admin account and skip user creation (default: Tiny11)
      --skip-user-creation     Skip manual user creation in OOBE and auto-create local account
      --auto-user [name]       Alias for --skip-user-creation (optional account name)
      --skip-autologon         Do not auto-logon to desktop when local account is created
      --fast                   Use LZX compression instead of LZMS (faster export)
      --keep-scratch           Do not delete scratch directory after completion
      --check-deps             Verify installed prerequisites and exit
  -h, --help                   Display this help message
```

---

## 💻 Virtual Machine Tips (Apple Silicon Mac)

When running Windows 11 ARM64 in virtual machines (UTM, VMware Fusion, Parallels):

### If Windows Setup asks to "Connect to a network"
If you performed a standard install without `--skip-user-creation` and the VM has no internet or missing network drivers:
1. In the VM window, press **Shift + F10** (or **Fn + Shift + F10** on Mac).
2. In the Command Prompt, type:
   ```cmd
   start ms-cxh:localonly
   ```
   and press **Enter**. This instantly bypasses the network screen and opens the local account creation page.
3. Alternatively, run `OOBE\BYPASSNRO` and press Enter to reboot into limited offline setup.

### Installing Network & Display Drivers in UTM
Windows 11 ARM64 does not bundle VirtIO drivers out of the box:
1. In the UTM top bar, click the CD icon and select **Install Windows Guest Tools** (or mount `spice-guest-tools.iso`).
2. Open Command Prompt with **Fn + Shift + F10**, navigate to `D:\` (or your CD drive), and run `spice-guest-tools-xxx.exe`.

---

## 🪟 Instructions: Windows (PowerShell)

1. Download Windows 11 from Microsoft or Rufus.
2. Mount the ISO in Windows Explorer.
3. Open **PowerShell 5.1** as Administrator.
4. Set execution policy:
   ```powershell
   Set-ExecutionPolicy Bypass -Scope Process
   ```
5. Run the builder script:
   ```powershell
   .\tiny11maker.ps1 -ISO <DriveLetter> -SCRATCH <DriveLetter>
   ```
6. Follow on-screen instructions to select the SKU edition.

---

## 🗑️ What Is Removed

| Tiny11maker | Tiny11coremaker |
| :--- | :--- |
| Clipchamp, News, Weather, Xbox, GetHelp, GetStarted, Office Hub, Solitaire, PeopleApp, PowerAutomate, ToDo, Alarms, Mail & Calendar, Feedback Hub, Maps, Sound Recorder, Phone Link, Media Player, QuickAssist, Edge, OneDrive, Copilot, Telemetry tasks | All from regular Tiny11 + Windows Component Store (WinSxS), Windows Defender, Windows Update, WinRE |

---

## 🧪 Testing

This repository includes automated test suites for the offline registry modifier, unattend generator, and WIM remastering pipeline:

```bash
# Run all unit and integration tests:
python3 scripts/test_unattend.py
python3 scripts/test_registry.py
python3 scripts/test_pipeline.py
```

---

## ❤️ Credits & Support

- Original concept and Windows scripts by **[ntdevlabs](https://github.com/ntdevlabs)**. Support the original creator:
  **[Patreon](http://patreon.com/ntdev) | [PayPal](http://paypal.me/ntdev2) | [Ko-fi](http://ko-fi.com/ntdev)**
- macOS and Linux port, offline registry engine, and unattended enhancements maintained by **[BrunoNFL](https://github.com/BrunoNFL)**.
