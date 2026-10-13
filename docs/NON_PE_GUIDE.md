# 📦 Non-PE Malware Analysis & Environment Guide

This guide provides end-to-end instructions for configuring the CAPEv2 Windows guest sandbox to dynamically detonate and monitor **all Non-PE formats** (Microsoft Office, RAR, 7-Zip, PDF, Java, Scripts, Python, Node.js, and AutoIt).

---

## 📑 Table of Contents

- [Overview](#overview)
- [Complete File Type & Package Matrix](#complete-file-type--package-matrix)
- [Why Analysis Fails Without Dedicated In-Guest Handlers](#why-analysis-fails-without-dedicated-in-guest-handlers)
- [Automated Bulk Software Installation (Chocolatey)](#automated-bulk-software-installation-chocolatey)
- [Microsoft Office Suite Automation (ODT)](#microsoft-office-suite-automation-odt)
  - [Silent ODT Deployment Configuration](#silent-odt-deployment-configuration)
  - [Registry Security Hardening (Macro & Protected View Bypass)](#registry-security-hardening-macro--protected-view-bypass)
- [Host-Side Decoders & Deobfuscators](#host-side-decoders--deobfuscators)
- [Step-by-Step Provisioning & Snapshotting Workflow](#step-by-step-provisioning--snapshotting-workflow)
- [Verification & Testing](#verification--testing)

---

## Overview

Unlike standard Windows executables (`.exe`, `.dll`) which detonate natively via Windows PE loader, **Non-PE malware** relies on external host applications (interpreters, document suites, archivers, and PDF readers) to execute its payload.

CAPEv2's guest analyzer (`analyzer.py`) maps submissions to execution packages located in `analyzer/windows/modules/packages/`. Each package searches for specific executables in standard paths. If an executable is missing, CAPEv2 raises a `CuckooPackageError` (e.g. `Unable to find any EXCEL.EXE executable` or `Unable to find any WinRAR.exe executable`).

---

## Complete File Type & Package Matrix

| Format | Extensions | CAPEv2 Package | In-Guest Executable | Search Path / Installation |
| :--- | :--- | :--- | :--- | :--- |
| **RAR Archive** | `.rar`, `.rev` | `rar.py` | `WinRAR.exe` | `C:\Program Files\WinRAR\WinRAR.exe` |
| **Multi-Archive** | `.zip`, `.7z`, `.tar`, `.gz`, `.iso`, `.cab` | `zip.py`, `archive.py` | `7z.exe` | `C:\Program Files\7-Zip\7z.exe` |
| **Excel Spreadsheet** | `.xls`, `.xlsx`, `.xlsm`, `.xlsb` | `xls.py`, `xls2016.py` | `EXCEL.EXE` | `C:\Program Files\Microsoft Office\Office*\EXCEL.EXE` |
| **Word Document** | `.doc`, `.docx`, `.docm`, `.rtf`, `.dotm` | `doc.py`, `doc2016.py` | `WINWORD.EXE` | `C:\Program Files\Microsoft Office\Office*\WINWORD.EXE` |
| **PowerPoint** | `.ppt`, `.pptx`, `.pptm`, `.pps` | `ppt.py`, `ppt2016.py` | `POWERPNT.EXE` | `C:\Program Files\Microsoft Office\Office*\POWERPNT.EXE` |
| **Access Database** | `.accdb`, `.mdb` | `access.py` | `MSACCESS.EXE` | `C:\Program Files\Microsoft Office\Office*\MSACCESS.EXE` |
| **Publisher** | `.pub` | `pub.py`, `pub2016.py` | `MSPUB.EXE` | `C:\Program Files\Microsoft Office\Office*\MSPUB.EXE` |
| **OneNote** | `.one` | `one.py` | `ONENOTE.EXE` | `C:\Program Files\Microsoft Office\Office*\ONENOTE.EXE` |
| **PDF Document** | `.pdf` | `pdf.py` | `SumatraPDF.exe` / `AcroRd32.exe` | `C:\Program Files\SumatraPDF\SumatraPDF.exe` |
| **Java Archive** | `.jar`, `.class` | `jar.py` | `javaw.exe` / `java.exe` | `C:\Program Files\Java\...\bin\javaw.exe` |
| **PowerShell** | `.ps1`, `.psm1`, `.psd1` | `ps1.py` | `powershell.exe` | `C:\Windows\System32\WindowsPowerShell\v1.0\` |
| **Batch / CMD** | `.bat`, `.cmd` | `batch.py` | `cmd.exe` | `C:\Windows\System32\cmd.exe` |
| **VBS / JS Script** | `.vbs`, `.vbe`, `.js`, `.wsf` | `vbs.py`, `js.py`, `wsf.py` | `wscript.exe` / `cscript.exe` | `C:\Windows\System32\wscript.exe` |
| **HTML Application** | `.hta` | `hta.py` | `mshta.exe` | `C:\Windows\System32\mshta.exe` |
| **AutoIt Script** | `.au3` | `autoit.py` | `AutoIt3.exe` | `C:\Program Files (x86)\AutoIt3\AutoIt3.exe` |
| **Node.js Script** | `.js`, `.mjs`, `.npm` | `nodejs.py` | `node.exe` | `C:\Program Files\nodejs\node.exe` |
| **Python Script** | `.py`, `.pyw` | `python.py` | `python.exe` | `C:\Program Files\Python310\python.exe` |
| **Email Message** | `.eml`, `.msg` | `eml.py`, `msg.py` | `OUTLOOK.EXE` | `C:\Program Files\Microsoft Office\Office*\OUTLOOK.EXE` |
| **Web / URL** | `.html`, `.url` | `chrome.py`, `edge.py` | `chrome.exe`, `msedge.exe`| `C:\Program Files\Google\Chrome\Application\` |
| **PE / DLL** | `.exe`, `.dll` | `exe.py`, `dll.py` | Native PE Loader | Requires VC++ Redistributables (2010–2022) |

---

## Why Analysis Fails Without Dedicated In-Guest Handlers

1. **RAR Archives (`rar.py`)**:
   - `rar.py` specifically verifies the presence of `WinRAR.exe`.
   - Python's `rarfile` library inside the Windows guest requires either `UnRAR.exe` or `WinRAR.exe` to parse headers and extract encrypted payloads. Even if 7-Zip is installed, `rar.py` will fail unless `WinRAR.exe` is present in `C:\Program Files\WinRAR`.
2. **Office Documents (`xls.py`, `doc.py`)**:
   - Dynamic macro analysis requires the real Microsoft Office executable to open the document, instantiate VBA macros, trigger `AutoOpen()` or `Workbook_Open()`, and detonate payload shellcode in memory.
   - Without `EXCEL.EXE` or `WINWORD.EXE`, the package cannot spawn the process, throwing `Unable to find any EXCEL.EXE executable`.

---

## Automated Bulk Software Installation (Chocolatey)

Instead of manually downloading and running multiple independent installers, the recommended approach is using **Chocolatey** directly inside the Windows guest VM to install all Non-PE software suites in one silent, automated command.

### In-Guest PowerShell Bulk Installation Command:

Open **Windows PowerShell as Administrator** inside the VM and run:

```powershell
# 1. Set execution policy to bypass
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072

# 2. Install Chocolatey Package Manager silently
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 3. Bulk install all CAPEv2 Non-PE software suites
choco install -y `
    winrar `
    7zip `
    sumatrapdf `
    javaruntime `
    nodejs-lts `
    autoit `
    vcredist-all `
    googlechrome `
    firefox
```

### What This Configures:
- **`winrar`**: Installs WinRAR 64-bit to `C:\Program Files\WinRAR\WinRAR.exe` (fixes `.rar` package).
- **`7zip`**: Installs 7-Zip to `C:\Program Files\7-Zip\7z.exe` and registers it in system `PATH`.
- **`sumatrapdf`**: Installs SumatraPDF to `C:\Program Files\SumatraPDF\SumatraPDF.exe` (fixes `.pdf` package).
- **`javaruntime`**: Deploys Java JRE and associates `.jar` execution with `javaw.exe`.
- **`nodejs-lts`**: Installs Node.js runtime for JavaScript malware detonation.
- **`autoit`**: Installs AutoIt3 interpreter for `.au3` compiled script detonation.
- **`vcredist-all`**: Installs all Microsoft Visual C++ Runtimes (2005 through 2022) to prevent missing DLL crashes.

---

## Microsoft Office Suite Automation (ODT)

Dynamic execution of malicious VBA and XL4 macros requires genuine Microsoft Office components. Microsoft provides the **Office Deployment Tool (ODT)** to install Office silently via official Microsoft CDNs.

### Silent ODT Deployment Configuration

1. Download the Office Deployment Tool (`setup.exe`) from [Microsoft's official site](https://www.microsoft.com/en-us/download/details.aspx?id=49117).
2. Create an unattended configuration file named `configuration.xml`:

```xml
<Configuration>
  <Add OfficeClientEdition="64" Channel="Current">
    <Product ID="ProPlus2019Retail">
      <Language ID="en-us" />
      <ExcludeApp ID="OneDrive" />
      <ExcludeApp ID="Teams" />
      <ExcludeApp ID="Skype" />
    </Product>
  </Add>
  <Display Level="None" AcceptEULA="TRUE" />
  <Property Name="AUTOACTIVATE" Value="0" />
</Configuration>
```

3. Run the silent installation from an elevated command prompt:
```cmd
setup.exe /configure configuration.xml
```
*Office Word, Excel, and PowerPoint will install silently in the background.*

---

### Registry Security Hardening (Macro & Protected View Bypass)

By default, Microsoft Office blocks macro execution and isolates downloaded documents in **Protected View**. For automated sandbox execution, these security mechanisms must be completely bypassed via registry keys.

Run the following in Administrator PowerShell inside the Windows guest:

```powershell
Write-Host "[*] Configuring Office Sandbox Security Bypass..." -ForegroundColor Yellow

$officeVersions = @("16.0", "15.0", "14.0")
$apps = @("Word", "Excel", "PowerPoint")

foreach ($ver in $officeVersions) {
    foreach ($app in $apps) {
        $securityPath = "HKCU:\Software\Microsoft\Office\$ver\$app\Security"
        New-Item -Path $securityPath -Force | Out-Null
        
        # Enable all macros without notification
        Set-ItemProperty -Path $securityPath -Name "VBAWarnings" -Value 1 -Force
        
        # Trust access to the VBA project object model
        Set-ItemProperty -Path $securityPath -Name "AccessVBOM" -Value 1 -Force
        
        # Disable Protected View for all sources
        $pvPath = "$securityPath\ProtectedView"
        New-Item -Path $pvPath -Force | Out-Null
        Set-ItemProperty -Path $pvPath -Name "DisableInternetFilesInPV" -Value 1 -Force
        Set-ItemProperty -Path $pvPath -Name "DisableUnsafeLocationsInPV" -Value 1 -Force
        Set-ItemProperty -Path $pvPath -Name "DisableAttachementsInPV" -Value 1 -Force
    }
    
    # Excel 4.0 (XLM) Macro bypass
    $excelSecurity = "HKCU:\Software\Microsoft\Office\$ver\Excel\Security"
    Set-ItemProperty -Path $excelSecurity -Name "XL4Macros" -Value 1 -Force
}

Write-Host "[+] Office Macro and Protected View bypass applied!" -ForegroundColor Green
```

---

## Host-Side Decoders & Deobfuscators

CAPEv2 also executes static extraction and deobfuscation on the Ubuntu host before or in parallel with dynamic detonation.

The installer framework (`./enable-nonpe.sh` or `./install.sh`) installs these Python modules directly into the isolated virtual environment (`/opt/CAPEv2/.venv`):

- **`oletools`**: Static VBA macro extraction (`olevba`, `mraptor`, `oleid`).
- **`xlmmacrodeobfuscator`**: Emulation and deobfuscation of Excel 4.0 (XLM) macros without requiring Office.
- **`batch_deobfuscator`**: Automated normalizer for obfuscated cmd/batch scripts.
- **`pdfminer.six`**: PDF stream parser and JavaScript extractor.
- **`httpreplay`**: Network stream replay engine.

---

## Step-by-Step Provisioning & Snapshotting Workflow

Follow this concise sequence whenever updating software in the Windows sandbox:

```
┌─────────────────────────────────┐
│  1. Run ./enable-nonpe.sh on    │  Updates host ISO on Drive E:
│     Ubuntu host                 │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│  2. Boot Windows VM & Execute   │  Installs WinRAR, 7-Zip, SumatraPDF,
│     Chocolatey / Office         │  Java, Office, disables Defender/UAC
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│  3. Verify Agent Port 8000      │  curl -I http://192.168.250.100:8000/
│     is HTTP 200 OK              │  (Wait for agent handshake)
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│  4. Capture Live Snapshot       │  virsh snapshot-create-as cape-win
│     cape-clean with RAM         │  cape-clean "Baseline with Non-PE"
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│  5. Restart CAPEv2 Services     │  sudo systemctl restart cape
└─────────────────────────────────┘
```

1. **Host-Side Preparation**:
   ```bash
   sudo ./enable-nonpe.sh
   ```
2. **Guest Configuration**:
   Open Windows PowerShell as Administrator inside `cape-win`:
   ```powershell
   # Install Chocolatey packages
   choco install -y winrar 7zip sumatrapdf javaruntime nodejs-lts autoit vcredist-all
   
   # Restart VM to clean up drivers and launch agent
   Restart-Computer
   ```
3. **Capture Running Baseline Snapshot**:
   Once the VM boots and `curl -I http://192.168.250.100:8000/` returns `HTTP 200 OK`:
   ```bash
   # Suppress services during snapshot capture
   sudo systemctl stop cape.service cape-processor.service
   
   # Purge existing snapshot block tag
   virsh qemu-monitor-command cape-win --hmp 'delvm cape-clean'
   
   # Capture fresh snapshot with live memory
   virsh snapshot-create-as cape-win cape-clean "Non-PE Baseline with WinRAR and Office"
   
   # Restart services
   sudo systemctl start cape.service cape-processor.service
   ```

---

## Verification & Testing

Verify that packages execute correctly by submitting sample Non-PE files via the web interface:

1. Submit a `.rar` file &rarr; verify task executes `rar.py` and extracts without `WinRAR.exe` errors.
2. Submit a `.xlsx` or `.xlsm` file &rarr; verify task executes `xls.py` and opens `EXCEL.EXE`.
3. Submit a `.pdf` file &rarr; verify task launches `SumatraPDF.exe`.
4. Submit a `.ps1` or `.vbs` file &rarr; verify execution trace captures script block logging and process trees.
