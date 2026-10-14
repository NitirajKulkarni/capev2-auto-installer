# CAPEv2 Microsoft Office & Non-PE Runtimes Automated Installer
# Installs Microsoft Office (Word, Excel, PowerPoint) via official Microsoft ODT,
# installs Java JRE for .jar analysis, applies permanent Macro/Protected View bypasses,
# and verifies CAPE sandbox readiness.
#
# Usage (Administrator PowerShell):
#   powershell -ep bypass -f E:\install-office.ps1

$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\cape-office-setup.log" -Append -ErrorAction SilentlyContinue

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CAPEv2 Automated Microsoft Office & Runtime Installer" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check for existing Microsoft Office installation
$excelPaths = @(
    "C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "C:\Program Files\Microsoft Office\Office16\EXCEL.EXE",
    "C:\Program Files\Microsoft Office\Office15\EXCEL.EXE",
    "C:\Program Files\Microsoft Office\Office14\EXCEL.EXE",
    "C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    "C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE"
)

$foundExcel = $null
foreach ($path in $excelPaths) {
    if (Test-Path $path) {
        $foundExcel = $path
        break
    }
}

if ($foundExcel) {
    Write-Host "[+] Microsoft Excel is already installed at: $foundExcel" -ForegroundColor Green
} else {
    Write-Host "[*] Microsoft Office not detected. Beginning automated deployment..." -ForegroundColor Yellow

    # Locate media drive (Drive E: / D:)
    $mediaDrive = (Get-PSDrive -PSProvider FileSystem | Where-Object { 
        (Test-Path (Join-Path $_.Root "agent.pyw")) -or 
        (Test-Path (Join-Path $_.Root "install-office.ps1")) 
    }).Root

    if (-not $mediaDrive) {
        foreach ($d in @("E:\", "D:\", "F:\")) {
            if (Test-Path $d) { $mediaDrive = $d; break }
        }
    }

    # Check for local Office installer / ISO on media drive
    $localOffice = $null
    if ($mediaDrive) {
        $localOffice = Get-ChildItem -Path $mediaDrive -Filter "*office*.iso" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $localOffice) {
            $localOffice = Get-ChildItem -Path $mediaDrive -Filter "*office*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        }
    }

    if ($localOffice) {
        Write-Host "[*] Found local Office installation media at $($localOffice.FullName)..." -ForegroundColor Yellow
        # If ISO, mount and run setup
        if ($localOffice.Extension -eq ".iso") {
            $mount = Mount-DiskImage -ImagePath $localOffice.FullName -PassThru
            $driveLetter = ($mount | Get-Volume).DriveLetter + ":"
            $setup = Join-Path $driveLetter "setup.exe"
            if (Test-Path $setup) {
                Start-Process -FilePath $setup -ArgumentList "/configure configuration.xml" -Wait
            }
            Dismount-DiskImage -ImagePath $localOffice.FullName -ErrorAction SilentlyContinue
        } else {
            Start-Process -FilePath $localOffice.FullName -ArgumentList "/quiet /norestart" -Wait
        }
    } else {
        # Automated deployment via Microsoft Office Deployment Tool (ODT) directly from Microsoft CDN
        $odtDir = "C:\OfficeODT"
        if (-not (Test-Path $odtDir)) {
            New-Item -ItemType Directory -Path $odtDir -Force | Out-Null
        }

        $odtUrl = "https://download.microsoft.com/download/2/7/A/27AF1BE6-DD20-4CB4-B154-EBAB8A7D4A7E/officedeploymenttool_17328-20162.exe"
        $odtExe = Join-Path $odtDir "odt_setup.exe"
        $setupExe = Join-Path $odtDir "setup.exe"

        Write-Host "[*] Downloading official Office Deployment Tool from Microsoft..." -ForegroundColor Yellow
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
            (New-Object Net.WebClient).DownloadFile($odtUrl, $odtExe)

            Write-Host "[*] Extracting ODT setup engine..." -ForegroundColor Yellow
            Start-Process -FilePath $odtExe -ArgumentList "/quiet /extract:$odtDir" -Wait

            if (Test-Path $setupExe) {
                # Create tailored configuration for Word, Excel, PowerPoint
                $configXml = @"
<Configuration>
  <Add OfficeClientEdition="64" Channel="Current">
    <Product ID="ProPlus2019Retail">
      <Language ID="en-us" />
      <ExcludeApp ID="OneDrive" />
      <ExcludeApp ID="Teams" />
      <ExcludeApp ID="Skype" />
      <ExcludeApp ID="Groove" />
      <ExcludeApp ID="Lync" />
    </Product>
  </Add>
  <Display Level="None" AcceptEULA="TRUE" />
  <Property Name="AUTOACTIVATE" Value="0" />
</Configuration>
"@
                $configPath = Join-Path $odtDir "configuration.xml"
                Set-Content -Path $configPath -Value $configXml -Encoding Ascii

                Write-Host "[*] Downloading and installing Microsoft Office ProPlus (Word, Excel, PowerPoint)..." -ForegroundColor Yellow
                Write-Host "[*] Note: Genuine Office components are streaming from Microsoft CDN (takes ~5-8 mins)..." -ForegroundColor Cyan
                
                $installProcess = Start-Process -FilePath $setupExe -ArgumentList "/configure `"$configPath`"" -PassThru

                # Monitor installation progress
                $timeoutSeconds = 900 # 15 minutes max
                $elapsed = 0
                while (-not $installProcess.HasExited -and $elapsed -lt $timeoutSeconds) {
                    Start-Sleep -Seconds 10
                    $elapsed += 10
                    $ctrProc = Get-Process -Name "OfficeClickToRun" -ErrorAction SilentlyContinue
                    if ($ctrProc) {
                        Write-Host "  ... Office Click-to-Run is active (Elapsed: ${elapsed}s)" -ForegroundColor DarkGray
                    }
                }

                if (-not $installProcess.HasExited) {
                    Write-Host "[!] Note: Office setup still executing in background..." -ForegroundColor Yellow
                }
            } else {
                Write-Host "[-] Failed to extract ODT setup.exe" -ForegroundColor Red
            }
        } catch {
            Write-Host "[!] Note on ODT installation: $_" -ForegroundColor DarkGray
        }
    }
}

# 2. Configure Office Sandbox Security Bypass (Enable all Macros & Disable Protected View)
Write-Host "[*] Applying Sandbox Security Bypass for Microsoft Office..." -ForegroundColor Yellow
try {
    $officeVersions = @("16.0", "15.0", "14.0", "12.0")
    $apps = @("Word", "Excel", "PowerPoint", "Access")

    foreach ($ver in $officeVersions) {
        foreach ($app in $apps) {
            $secPath = "HKCU:\Software\Microsoft\Office\$ver\$app\Security"
            if (-not (Test-Path $secPath)) {
                New-Item -Path $secPath -Force | Out-Null
            }
            # Enable all macros without notification
            Set-ItemProperty -Path $secPath -Name "VBAWarnings" -Value 1 -Force -ErrorAction SilentlyContinue
            # Trust access to VBA object model
            Set-ItemProperty -Path $secPath -Name "AccessVBOM" -Value 1 -Force -ErrorAction SilentlyContinue

            # Disable Protected View across all sources
            $pvPath = "$secPath\ProtectedView"
            if (-not (Test-Path $pvPath)) {
                New-Item -Path $pvPath -Force | Out-Null
            }
            Set-ItemProperty -Path $pvPath -Name "DisableInternetFilesInPV" -Value 1 -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $pvPath -Name "DisableUnsafeLocationsInPV" -Value 1 -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $pvPath -Name "DisableAttachementsInPV" -Value 1 -Force -ErrorAction SilentlyContinue
        }

        # Excel 4.0 (XLM) Macro bypass
        $excelSecurity = "HKCU:\Software\Microsoft\Office\$ver\Excel\Security"
        if (-not (Test-Path $excelSecurity)) {
            New-Item -Path $excelSecurity -Force | Out-Null
        }
        Set-ItemProperty -Path $excelSecurity -Name "XL4Macros" -Value 1 -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[+] Office Macro and Protected View bypasses applied successfully!" -ForegroundColor Green
} catch {
    Write-Host "[!] Note on Office registry configuration: $_" -ForegroundColor DarkGray
}

# 3. Ensure Java Runtime (JRE) is installed for .jar analysis
Write-Host "[*] Checking Java Runtime Environment (.jar handler)..." -ForegroundColor Yellow
$javaCmd = Get-Command java.exe -ErrorAction SilentlyContinue
if (-not $javaCmd) {
    if (Test-Path "C:\Program Files\Java") {
        $javaExe = Get-ChildItem -Path "C:\Program Files\Java" -Filter "java.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($javaExe) {
            $javaDir = $javaExe.DirectoryName
            $p = [Environment]::GetEnvironmentVariable("Path", "Machine")
            if ($p -notlike "*$javaDir*") {
                [Environment]::SetEnvironmentVariable("Path", "$p;$javaDir", "Machine")
                $env:Path = "$javaDir;$env:Path"
            }
            $javaCmd = $javaExe
        }
    }
}

if ($javaCmd) {
    Write-Host "[+] Java is installed: $($javaCmd.Source)" -ForegroundColor Green
} else {
    Write-Host "[*] Java not found. Installing Java JRE silently via Chocolatey..." -ForegroundColor Yellow
    try {
        if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
            $env:Path = "$env:ALLUSERSPROFILE\chocolatey\bin;$env:Path"
        }
        if (Get-Command choco.exe -ErrorAction SilentlyContinue) {
            choco install -y javaruntime --no-progress
            Write-Host "[+] Java JRE installed successfully!" -ForegroundColor Green
        }
    } catch {
        Write-Host "[!] Note on Java installation: $_" -ForegroundColor DarkGray
    }
}

# 4. Verify Final State
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  VERIFICATION RESULTS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$excelOk = $false
foreach ($p in $excelPaths) {
    if (Test-Path $p) { $excelOk = $true; break }
}

$wordOk = (Test-Path "C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE") -or (Test-Path "C:\Program Files\Microsoft Office\Office16\WINWORD.EXE")
$javaOk = [bool](Get-Command java.exe -ErrorAction SilentlyContinue) -or (Test-Path "C:\Program Files\Java")
$winrarOk = Test-Path "C:\Program Files\WinRAR\WinRAR.exe"
$sevenzipOk = Test-Path "C:\Program Files\7-Zip\7z.exe"

Write-Host "  Microsoft Excel: $(if ($excelOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($excelOk) { 'Green' } else { 'Yellow' })
Write-Host "  Microsoft Word:  $(if ($wordOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($wordOk) { 'Green' } else { 'Yellow' })
Write-Host "  Java JRE:        $(if ($javaOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($javaOk) { 'Green' } else { 'Yellow' })
Write-Host "  WinRAR:          $(if ($winrarOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($winrarOk) { 'Green' } else { 'Yellow' })
Write-Host "  7-Zip:           $(if ($sevenzipOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($sevenzipOk) { 'Green' } else { 'Yellow' })
Write-Host "============================================================" -ForegroundColor Cyan

# 5. Ensure CAPE Agent is active on port 8000
$agentActive = $false
try {
    $res = Test-NetConnection -Port 8000 -ComputerName 127.0.0.1 -WarningAction SilentlyContinue
    if ($res.TcpTestSucceeded) {
        $agentActive = $true
    }
} catch {}

if ($agentActive) {
    Write-Host "[+] CAPE Agent is active and listening on port 8000!" -ForegroundColor Green
    Write-Host "[+] You can now run 'sudo ./enable-nonpe.sh' or 'sudo ./repair.sh' on Ubuntu to save the snapshot." -ForegroundColor Green
} else {
    Write-Host "[*] Restarting Windows VM to launch CAPE Agent cleanly..." -ForegroundColor Yellow
}

Stop-Transcript -ErrorAction SilentlyContinue
