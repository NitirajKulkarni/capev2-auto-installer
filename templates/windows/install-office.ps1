# CAPEv2 Microsoft Office & Non-PE Runtimes Automated Installer (100% Offline)
# Installs Microsoft Office 2019 (Word, Excel, PowerPoint) from preloaded host media
# via Click-to-Run / Office Deployment Tool (officedeploymenttool engine),
# installs Java JRE for .jar analysis, applies permanent Macro/Protected View bypasses,
# and verifies CAPE sandbox readiness.
#
# Usage (Administrator PowerShell):
#   powershell -ep bypass -f E:\install-office.ps1

$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\cape-office-setup.log" -Append -ErrorAction SilentlyContinue

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CAPEv2 Automated Microsoft Office & Runtime Installer" -ForegroundColor Cyan
Write-Host "  (100% Offline Host-Preloaded Architecture)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Helper function to append to System Machine PATH
function Add-ToSystemPath {
    param([string]$Dir)
    if (Test-Path $Dir) {
        $curr = [Environment]::GetEnvironmentVariable("Path", "Machine")
        if ($curr -notlike "*$Dir*") {
            [Environment]::SetEnvironmentVariable("Path", "$curr;$Dir", "Machine")
            $env:Path = "$Dir;$env:Path"
            Write-Host "[+] Added '$Dir' to System PATH" -ForegroundColor Green
        }
    }
}

# 1. Drive & Media Discovery
Write-Host "[*] Discovering system drives and attached installation media..." -ForegroundColor Yellow
$allDrives = Get-PSDrive -PSProvider FileSystem | Select-Object -ExpandProperty Root

$mediaDrive = $null
foreach ($d in $allDrives) {
    if ((Test-Path (Join-Path $d "agent.pyw")) -or 
        (Test-Path (Join-Path $d "install-office.ps1")) -or 
        (Test-Path (Join-Path $d "python-installer.exe"))) {
        $mediaDrive = $d
        break
    }
}
if (-not $mediaDrive) {
    foreach ($d in @("E:\", "D:\", "F:\", "G:\")) {
        if (Test-Path $d) { $mediaDrive = $d; break }
    }
}
Write-Host "[+] Tools & Agent media drive: $($mediaDrive ?? 'Not found (using C:\)')" -ForegroundColor $(if ($mediaDrive) { "Green" } else { "Yellow" })

# 2. Check for existing Microsoft Office installation
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
    Write-Host "[+] Microsoft Office is already installed: $foundExcel" -ForegroundColor Green
} else {
    Write-Host "[*] Microsoft Office not detected. Locating preloaded offline installation media..." -ForegroundColor Yellow

    # Discover Office Drive (attached as secondary optical drive or ISO/IMG)
    $officeDrive = $null
    $mountedIso = $null

    # A) Check each drive for Setup.exe and Office\Setup64.exe or Office\data
    foreach ($d in $allDrives) {
        $setup64 = Join-Path $d "Office\Setup64.exe"
        $officeData = Join-Path $d "Office\data"
        $rootSetup = Join-Path $d "Setup.exe"
        if ((Test-Path $setup64) -or (Test-Path $officeData) -or ((Test-Path $rootSetup) -and ($d -ne $mediaDrive))) {
            $officeDrive = $d
            Write-Host "[+] Detected Office 2019 media on drive: $officeDrive" -ForegroundColor Green
            break
        }
    }

    # B) If not found as an attached drive, check for .iso or .img files on media drive or C:\
    if (-not $officeDrive) {
        $searchDirs = @($mediaDrive, "C:\", "D:\", "E:\") | Where-Object { $_ -and (Test-Path $_) }
        $isoCandidates = @()
        foreach ($sdir in $searchDirs) {
            $isoCandidates += Get-ChildItem -Path $sdir -Filter "*office*.iso" -ErrorAction SilentlyContinue
            $isoCandidates += Get-ChildItem -Path $sdir -Filter "*office*.img" -ErrorAction SilentlyContinue
            $isoCandidates += Get-ChildItem -Path $sdir -Filter "*ProPlus*.img" -ErrorAction SilentlyContinue
            $isoCandidates += Get-ChildItem -Path $sdir -Filter "*ProPlus*.iso" -ErrorAction SilentlyContinue
        }

        $isoFile = $isoCandidates | Select-Object -First 1
        if ($isoFile) {
            Write-Host "[*] Found Office disk image at '$($isoFile.FullName)'. Mounting image..." -ForegroundColor Yellow
            try {
                $mount = Mount-DiskImage -ImagePath $isoFile.FullName -PassThru
                $letter = ($mount | Get-Volume).DriveLetter
                if ($letter) {
                    $officeDrive = "$letter`:\"
                    $mountedIso = $isoFile.FullName
                    Write-Host "[+] Mounted Office image as drive $officeDrive" -ForegroundColor Green
                }
            } catch {
                Write-Host "[!] Could not mount disk image: $_" -ForegroundColor DarkGray
            }
        }
    }

    if ($officeDrive) {
        Write-Host "[*] Executing 100% offline Microsoft Office 2019 installation from $officeDrive..." -ForegroundColor Yellow

        $odtDir = "C:\OfficeODT"
        if (-not (Test-Path $odtDir)) {
            New-Item -ItemType Directory -Path $odtDir -Force | Out-Null
        }

        # Create tailored offline configuration XML
        $configXml = @"
<Configuration>
  <Add SourcePath="$officeDrive" OfficeClientEdition="64">
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

        $setupExe = Join-Path $officeDrive "Setup.exe"
        $setup64Exe = Join-Path $officeDrive "Office\Setup64.exe"

        $installerProc = $null
        if (Test-Path $setupExe) {
            Write-Host "[*] Running: $setupExe /configure $configPath" -ForegroundColor Yellow
            $installerProc = Start-Process -FilePath $setupExe -ArgumentList "/configure `"$configPath`"" -PassThru
        } elseif (Test-Path $setup64Exe) {
            Write-Host "[*] Running: $setup64Exe" -ForegroundColor Yellow
            $installerProc = Start-Process -FilePath $setup64Exe -PassThru
        }

        # Wait for Office Click-to-Run installation to complete
        Write-Host "[*] Installing Microsoft Office components silently in background (takes ~3-6 minutes)..." -ForegroundColor Cyan
        $timeoutSeconds = 900
        $elapsed = 0
        while ($elapsed -lt $timeoutSeconds) {
            Start-Sleep -Seconds 10
            $elapsed += 10
            $ctr = Get-Process -Name "OfficeClickToRun" -ErrorAction SilentlyContinue
            if ($ctr) {
                Write-Host "  ... Office Click-to-Run is actively installing components (Elapsed: ${elapsed}s)" -ForegroundColor DarkGray
            } else {
                # If OfficeClickToRun has exited, check if Excel exists
                $installed = $false
                foreach ($p in $excelPaths) {
                    if (Test-Path $p) { $installed = $true; break }
                }
                if ($installed) {
                    Write-Host "[+] Office installation finished successfully in ${elapsed}s!" -ForegroundColor Green
                    break
                }
                if ($elapsed -ge 60 -and -not $ctr) {
                    Write-Host "[*] OfficeClickToRun finished." -ForegroundColor Yellow
                    break
                }
            }
        }

        if ($mountedIso) {
            Dismount-DiskImage -ImagePath $mountedIso -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "[-] Office installation media not detected on any optical drive or path!" -ForegroundColor Yellow
        Write-Host "    To install Office completely offline:" -ForegroundColor Cyan
        Write-Host "    Run 'sudo ./enable-nonpe.sh' on your Ubuntu host." -ForegroundColor Cyan
        Write-Host "    This auto-downloads the Office 2019 media and attaches it as Drive F: to this VM." -ForegroundColor Cyan
    }
}

# 3. Configure Office Sandbox Security Bypass (Enable all Macros & Disable Protected View)
Write-Host "[*] Configuring Microsoft Office Sandbox Security Bypass..." -ForegroundColor Yellow
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

    # Disable First-Run screens, Welcome popups, and Privacy prompts
    $commonGeneral = "HKCU:\Software\Microsoft\Office\16.0\Common\General"
    if (-not (Test-Path $commonGeneral)) { New-Item -Path $commonGeneral -Force | Out-Null }
    Set-ItemProperty -Path $commonGeneral -Name "ShownFirstRunOptin" -Value 1 -Force -ErrorAction SilentlyContinue

    $commonPT = "HKCU:\Software\Microsoft\Office\16.0\Common\PTAware"
    if (-not (Test-Path $commonPT)) { New-Item -Path $commonPT -Force | Out-Null }
    Set-ItemProperty -Path $commonPT -Name "PTAware" -Value 1 -Force -ErrorAction SilentlyContinue

    $commonPrivacy = "HKCU:\Software\Microsoft\Office\16.0\Common\Privacy"
    if (-not (Test-Path $commonPrivacy)) { New-Item -Path $commonPrivacy -Force | Out-Null }
    Set-ItemProperty -Path $commonPrivacy -Name "DisconnectedState" -Value 2 -Force -ErrorAction SilentlyContinue

    Write-Host "[+] Office Macro and Protected View bypasses applied successfully!" -ForegroundColor Green
} catch {
    Write-Host "[!] Note on Office registry configuration: $_" -ForegroundColor DarkGray
}

# 4. Ensure Java Runtime (JRE) is installed for .jar analysis (100% Offline)
Write-Host "[*] Checking Java Runtime Environment (.jar handler)..." -ForegroundColor Yellow
$javaCmd = Get-Command java.exe -ErrorAction SilentlyContinue
if (-not $javaCmd) {
    # Scan standard locations
    $searchPaths = @(
        "C:\Program Files\Eclipse Adoptium",
        "C:\Program Files\Java",
        "C:\Program Files (x86)\Java"
    )
    foreach ($sp in $searchPaths) {
        if (Test-Path $sp) {
            $javaExe = Get-ChildItem -Path $sp -Filter "java.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($javaExe) {
                Add-ToSystemPath $javaExe.DirectoryName
                $javaCmd = $javaExe
                break
            }
        }
    }
}

if ($javaCmd) {
    Write-Host "[+] Java is installed and registered in PATH: $($javaCmd.Source ?? $javaCmd.FullName)" -ForegroundColor Green
} else {
    Write-Host "[*] Java not found. Searching for preloaded OpenJDK offline installer..." -ForegroundColor Yellow

    # Search for OpenJDK MSI on media drive or any drive
    $javaMsi = $null
    if ($mediaDrive) {
        $javaMsi = Get-ChildItem -Path $mediaDrive -Filter "*openjdk*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $javaMsi) {
            $javaMsi = Get-ChildItem -Path $mediaDrive -Filter "*jre*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
        }
    }

    if (-not $javaMsi) {
        foreach ($d in $allDrives) {
            $javaMsi = Get-ChildItem -Path $d -Filter "*openjdk*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($javaMsi) { break }
        }
    }

    if ($javaMsi) {
        Write-Host "[*] Installing Adoptium OpenJDK JRE silently from $($javaMsi.FullName)..." -ForegroundColor Yellow
        $p = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$($javaMsi.FullName)`" /qn ADDLOCAL=FeatureMain,FeatureJavaHome,FeatureJarFileRunWith,FeatureOracleJavaSoft /norestart" -Wait -PassThru
        Write-Host "[+] OpenJDK MSI installer finished (ExitCode: $($p.ExitCode))" -ForegroundColor Green

        # Register in PATH
        $adoptiumExe = Get-ChildItem -Path "C:\Program Files\Eclipse Adoptium" -Filter "java.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($adoptiumExe) {
            Add-ToSystemPath $adoptiumExe.DirectoryName
            Write-Host "[+] Java registered in System PATH: $($adoptiumExe.FullName)" -ForegroundColor Green
        }
    } else {
        # Check if internet is available before trying Chocolatey
        $isOnline = $false
        try {
            $testConn = Test-NetConnection -ComputerName "8.8.8.8" -Port 53 -WarningAction SilentlyContinue
            if ($testConn.TcpTestSucceeded) { $isOnline = $true }
        } catch {}

        if ($isOnline) {
            Write-Host "[*] Internet detected. Installing Java via Chocolatey..." -ForegroundColor Yellow
            try {
                if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
                    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
                    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
                    $env:Path = "$env:ALLUSERSPROFILE\chocolatey\bin;$env:Path"
                }
                if (Get-Command choco.exe -ErrorAction SilentlyContinue) {
                    choco install -y javaruntime --no-progress
                    Write-Host "[+] Java JRE installed successfully via Chocolatey!" -ForegroundColor Green
                }
            } catch {
                Write-Host "[!] Chocolatey installation note: $_" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "[!] Offline mode: Java MSI installer not found on drive $mediaDrive" -ForegroundColor Yellow
            Write-Host "    Ensure 'sudo ./enable-nonpe.sh' was run on the Ubuntu host to bake openjdk-installer.msi into Drive E:." -ForegroundColor Cyan
        }
    }
}

# 5. Verify Final State
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  VERIFICATION RESULTS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$excelOk = $false
foreach ($p in $excelPaths) {
    if (Test-Path $p) { $excelOk = $true; break }
}

$wordOk = (Test-Path "C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE") -or (Test-Path "C:\Program Files\Microsoft Office\Office16\WINWORD.EXE")
$javaOk = [bool](Get-Command java.exe -ErrorAction SilentlyContinue) -or (Test-Path "C:\Program Files\Eclipse Adoptium") -or (Test-Path "C:\Program Files\Java")
$winrarOk = Test-Path "C:\Program Files\WinRAR\WinRAR.exe"
$sevenzipOk = Test-Path "C:\Program Files\7-Zip\7z.exe"
$sumatraOk = Test-Path "C:\Program Files\SumatraPDF\SumatraPDF.exe"

Write-Host "  Microsoft Excel: $(if ($excelOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($excelOk) { 'Green' } else { 'Yellow' })
Write-Host "  Microsoft Word:  $(if ($wordOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($wordOk) { 'Green' } else { 'Yellow' })
Write-Host "  Java JRE:        $(if ($javaOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($javaOk) { 'Green' } else { 'Yellow' })
Write-Host "  WinRAR:          $(if ($winrarOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($winrarOk) { 'Green' } else { 'Yellow' })
Write-Host "  7-Zip:           $(if ($sevenzipOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($sevenzipOk) { 'Green' } else { 'Yellow' })
Write-Host "  SumatraPDF:      $(if ($sumatraOk) { '[+] READY' } else { '[-] NOT FOUND' })" -ForegroundColor $(if ($sumatraOk) { 'Green' } else { 'Yellow' })
Write-Host "============================================================" -ForegroundColor Cyan

# 6. Ensure CAPE Agent is active on port 8000
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
    Write-Host "[*] Starting CAPEv2 Agent daemon in background..." -ForegroundColor Yellow
    $pythonExe = "C:\Program Files\Python310\python.exe"
    $pythonwExe = "C:\Program Files\Python310\pythonw.exe"
    $startupAgent = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\agent.pyw"

    if (Test-Path $startupAgent) {
        if (Test-Path $pythonwExe) {
            Start-Process -FilePath $pythonwExe -ArgumentList "`"$startupAgent`"" -WindowStyle Hidden
        } elseif (Test-Path $pythonExe) {
            Start-Process -FilePath $pythonExe -ArgumentList "`"$startupAgent`"" -WindowStyle Hidden
        }
    }
}

Stop-Transcript -ErrorAction SilentlyContinue
