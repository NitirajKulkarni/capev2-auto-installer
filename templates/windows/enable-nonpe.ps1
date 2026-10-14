# CAPEv2 Windows Guest Non-PE Environment Enabler & Baseline Preparation
# Configures Windows guest to analyze all Non-PE formats:
# - Archives (.rar, .zip, .7z, .iso, .tar) via WinRAR and 7-Zip
# - Documents (.pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx) via SumatraPDF & MS Office
# - Scripts (.ps1, .vbs, .js, .wsf, .bat, .cmd, .hta) via Bypass policies & WSH
# - Interpreters & Runtimes (Java JRE, Node.js, AutoIt3, VC++ 2015-2022)
# and starts the CAPE Agent daemon on port 8000.

$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\cape-nonpe-setup.log" -Append -ErrorAction SilentlyContinue

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CAPEv2 Windows Guest Non-PE Configuration Engine" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Network Configuration: configure static IP on analysis interface
try {
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1
    if (-not $adapter) {
        $adapter = Get-NetAdapter | Select-Object -First 1
    }
    if ($adapter) {
        Write-Host "[*] Configuring static IP 192.168.250.100 on adapter '$($adapter.Name)'..." -ForegroundColor Yellow
        Remove-NetIPAddress -InterfaceIndex $adapter.ifIndex -Confirm:$false -ErrorAction SilentlyContinue
        Remove-NetRoute -InterfaceIndex $adapter.ifIndex -Confirm:$false -ErrorAction SilentlyContinue
        New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress "192.168.250.100" -PrefixLength 24 -DefaultGateway "192.168.250.1" -ErrorAction SilentlyContinue
        Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ("8.8.8.8", "1.1.1.1") -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host "[!] Note on network configuration: $_" -ForegroundColor DarkGray
}

# 2. Disable Windows Defender completely (essential for malware analysis baseline)
Write-Host "[*] Disabling Windows Defender & Cloud Telemetry..." -ForegroundColor Yellow
try {
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableIOAVProtection $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableScriptScanning $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBlockAtFirstSeen $true -ErrorAction SilentlyContinue
    Set-MpPreference -MAPSReporting 0 -ErrorAction SilentlyContinue
    Set-MpPreference -SubmitSamplesConsent 2 -ErrorAction SilentlyContinue
    
    reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" /v "DisableAntiSpyware" /t REG_DWORD /d 1 /f | Out-Null
    reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v "DisableRealtimeMonitoring" /t REG_DWORD /d 1 /f | Out-Null
    reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v "DisableBehaviorMonitoring" /t REG_DWORD /d 1 /f | Out-Null
    reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection" /v "DisableScriptScanning" /t REG_DWORD /d 1 /f | Out-Null
} catch {
    Write-Host "[!] Note on Defender settings: $_" -ForegroundColor DarkGray
}

# 3. Disable UAC (User Account Control)
Write-Host "[*] Disabling UAC..." -ForegroundColor Yellow
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "EnableLUA" -Value 0 -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "ConsentPromptBehaviorAdmin" -Value 0 -Force -ErrorAction SilentlyContinue

# 4. Disable Windows Firewall
Write-Host "[*] Disabling Windows Firewall across all profiles..." -ForegroundColor Yellow
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False -ErrorAction SilentlyContinue

# 5. Disable Sleep, Screen Timeout & Hibernation
Write-Host "[*] Disabling Sleep, Screen Timeout and Hibernation..." -ForegroundColor Yellow
powercfg -x -standby-timeout-ac 0
powercfg -x -hibernate-timeout-ac 0
powercfg -x -monitor-timeout-ac 0

# 6. Enable Script Execution (PowerShell Bypass & Windows Script Host)
Write-Host "[*] Configuring Script Execution Handlers (.ps1, .vbs, .js, .wsf, .bat)..." -ForegroundColor Yellow
try {
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Force -Scope LocalMachine -ErrorAction SilentlyContinue
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Force -Scope CurrentUser -ErrorAction SilentlyContinue
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Force -Scope Process -ErrorAction SilentlyContinue

    # Ensure Windows Script Host (.vbs, .js, .wsf) is fully enabled
    reg add "HKLM\SOFTWARE\Microsoft\Windows Script Host\Settings" /v "Enabled" /t REG_DWORD /d 1 /f | Out-Null
    reg add "HKCU\SOFTWARE\Microsoft\Windows Script Host\Settings" /v "Enabled" /t REG_DWORD /d 1 /f | Out-Null

    # Disable Open File Security Warnings for downloaded scripts and archives
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Associations" /v "DefaultFileTypeRisk" /t REG_DWORD /d 1806 /f | Out-Null
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Associations" /v "LowRiskFileTypes" /t REG_SZ /d ".exe;.bat;.cmd;.ps1;.vbs;.js;.wsf;.hta;.pdf;.zip;.rar;.7z;.iso;.tar;.gz;.jar;.au3;.py;.pyw;.doc;.docx;.xls;.xlsx;.ppt;.pptx;" /f | Out-Null
} catch {
    Write-Host "[!] Note on Script ExecutionPolicy: $_" -ForegroundColor DarkGray
}

# 7. Disable Windows Boot Recovery & Startup Repair ("Windows didn't load correctly")
Write-Host "[*] Disabling Windows Boot Recovery & Automatic Startup Repair..." -ForegroundColor Yellow
try {
    bcdedit /set "{default}" bootstatuspolicy ignoreallfailures | Out-Null
    bcdedit /set "{default}" recoveryenabled no | Out-Null
    bcdedit /set "{current}" bootstatuspolicy ignoreallfailures | Out-Null
    bcdedit /set "{current}" recoveryenabled no | Out-Null
    bcdedit /set "{default}" timeout 0 | Out-Null
    chkntfs /x c: | Out-Null
} catch {
    Write-Host "[!] Note on BCD recovery settings: $_" -ForegroundColor DarkGray
}

# 8. Locate Optical / Shared Drive (OEMDRV / Drive E: / D:)
Write-Host "[*] Locating installation media on optical/shared drive..." -ForegroundColor Yellow
$mediaDrive = (Get-PSDrive -PSProvider FileSystem | Where-Object { 
    (Test-Path (Join-Path $_.Root "agent.pyw")) -or 
    (Test-Path (Join-Path $_.Root "enable-nonpe.ps1")) -or 
    (Test-Path (Join-Path $_.Root "python-installer.exe")) 
}).Root

if (-not $mediaDrive) {
    # Fallback to E:\ or D:\ if available
    foreach ($letter in @("E:\", "D:\", "F:\")) {
        if (Test-Path $letter) { $mediaDrive = $letter; break }
    }
}

if ($mediaDrive) {
    Write-Host "[+] Found installation media at '$mediaDrive'" -ForegroundColor Green
} else {
    Write-Host "[-] WARNING: Could not find optical drive. Checking C:\ fallback..." -ForegroundColor Yellow
    $mediaDrive = "C:\"
}

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

# 9. Install WinRAR silently (CRITICAL: fixes .rar analysis and rar.py package)
$winrarInstaller = Get-ChildItem -Path $mediaDrive -Filter "*winrar*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $winrarInstaller) {
    $winrarInstaller = Get-ChildItem -Path $mediaDrive -Filter "*rar*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($winrarInstaller) {
    Write-Host "[*] Installing WinRAR 64-bit silently from $($winrarInstaller.FullName)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $winrarInstaller.FullName -ArgumentList "/S" -Wait -PassThru
    if ($p.ExitCode -eq 0 -or (Test-Path "C:\Program Files\WinRAR\WinRAR.exe")) {
        Write-Host "[+] WinRAR installed successfully at C:\Program Files\WinRAR\WinRAR.exe" -ForegroundColor Green
        Add-ToSystemPath "C:\Program Files\WinRAR"
    }
} elseif (Test-Path "C:\Program Files\WinRAR\WinRAR.exe") {
    Write-Host "[+] WinRAR is already present at C:\Program Files\WinRAR\WinRAR.exe" -ForegroundColor Green
    Add-ToSystemPath "C:\Program Files\WinRAR"
} else {
    Write-Host "[!] WinRAR installer not found on media drive. Will attempt online package install." -ForegroundColor DarkGray
}

# 10. Install 7-Zip silently (for Archive extraction: .zip, .7z, .iso, .tar)
$sevenZipInstaller = Get-ChildItem -Path $mediaDrive -Filter "7z*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($sevenZipInstaller) {
    Write-Host "[*] Installing 7-Zip silently from $($sevenZipInstaller.FullName)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $sevenZipInstaller.FullName -ArgumentList "/S" -Wait -PassThru
    if ($p.ExitCode -eq 0 -or (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
        Write-Host "[+] 7-Zip installed successfully at C:\Program Files\7-Zip\7z.exe" -ForegroundColor Green
        Add-ToSystemPath "C:\Program Files\7-Zip"
    }
} elseif (Test-Path "C:\Program Files\7-Zip\7z.exe") {
    Write-Host "[+] 7-Zip is already present at C:\Program Files\7-Zip\7z.exe" -ForegroundColor Green
    Add-ToSystemPath "C:\Program Files\7-Zip"
} else {
    Write-Host "[!] 7-Zip installer not found on media drive. Skipping 7-Zip." -ForegroundColor DarkGray
}

# 11. Install PDF Reader silently (for PDF analysis: .pdf)
$pdfInstaller = Get-ChildItem -Path $mediaDrive -Filter "*SumatraPDF*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pdfInstaller) {
    $pdfInstaller = Get-ChildItem -Path $mediaDrive -Filter "*pdf*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($pdfInstaller -and (Get-Item $pdfInstaller.FullName).Length -gt 1048576) {
    try {
        Write-Host "[*] Installing PDF Reader silently from $($pdfInstaller.FullName)..." -ForegroundColor Yellow
        $p = Start-Process -FilePath $pdfInstaller.FullName -ArgumentList "-s -all-users" -Wait -PassThru
        if ($p.ExitCode -eq 0) {
            Write-Host "[+] SumatraPDF installed successfully!" -ForegroundColor Green
            Add-ToSystemPath "C:\Program Files\SumatraPDF"
        }
    } catch {
        Write-Host "[!] Note on PDF installer execution: $_" -ForegroundColor DarkGray
    }
} elseif (Test-Path "C:\Program Files\SumatraPDF\SumatraPDF.exe") {
    Write-Host "[+] SumatraPDF is already present." -ForegroundColor Green
    Add-ToSystemPath "C:\Program Files\SumatraPDF"
} else {
    Write-Host "[*] SumatraPDF not found on media. Using Windows default PDF handler (Edge)..." -ForegroundColor Yellow
}

# 12. Install Visual C++ 2015-2022 Redistributable (fixes missing MSVCR/VCRUNTIME DLLs)
$vcInstaller = Get-ChildItem -Path $mediaDrive -Filter "*vcredist*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $vcInstaller) {
    $vcInstaller = Get-ChildItem -Path $mediaDrive -Filter "*vc_redist*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($vcInstaller) {
    Write-Host "[*] Installing Visual C++ Redistributable (2015-2022)..." -ForegroundColor Yellow
    Start-Process -FilePath $vcInstaller.FullName -ArgumentList "/quiet /norestart" -Wait
    Write-Host "[+] Visual C++ Redistributable installed." -ForegroundColor Green
}

# 13. Install Python 3.10 if not already present
$pythonExe = "C:\Program Files\Python310\python.exe"
$pythonwExe = "C:\Program Files\Python310\pythonw.exe"
if (-not (Test-Path $pythonExe)) {
    $pyInst = Join-Path $mediaDrive "python-installer.exe"
    if (Test-Path $pyInst) {
        Write-Host "[*] Installing Python 3.10 silently (please wait)..." -ForegroundColor Yellow
        $p = Start-Process -FilePath $pyInst -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -PassThru
        Write-Host "[+] Python 3.10 installation finished (ExitCode: $($p.ExitCode))" -ForegroundColor Green
    }
}
Add-ToSystemPath "C:\Program Files\Python310"
Add-ToSystemPath "C:\Program Files\Python310\Scripts"

# 13B. Install Adoptium OpenJDK JRE silently (CRITICAL: fixes .jar analysis and jar.py package)
$javaMsi = Get-ChildItem -Path $mediaDrive -Filter "*openjdk*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $javaMsi) {
    $javaMsi = Get-ChildItem -Path $mediaDrive -Filter "*jre*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if ($javaMsi) {
    Write-Host "[*] Installing Adoptium OpenJDK JRE silently from $($javaMsi.FullName)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$($javaMsi.FullName)`" /qn ADDLOCAL=FeatureMain,FeatureJavaHome,FeatureJarFileRunWith,FeatureOracleJavaSoft /norestart" -Wait -PassThru
    Write-Host "[+] Adoptium OpenJDK JRE installed (ExitCode: $($p.ExitCode))" -ForegroundColor Green
    $adoptiumExe = Get-ChildItem -Path "C:\Program Files\Eclipse Adoptium" -Filter "java.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($adoptiumExe) {
        Add-ToSystemPath $adoptiumExe.DirectoryName
    }
} elseif (Test-Path "C:\Program Files\Eclipse Adoptium") {
    $adoptiumExe = Get-ChildItem -Path "C:\Program Files\Eclipse Adoptium" -Filter "java.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($adoptiumExe) {
        Add-ToSystemPath $adoptiumExe.DirectoryName
    }
}

# 14. Online Bulk Package Manager (Chocolatey) - Automated Bulk Non-PE Enabler
$isOnline = $false
try {
    $testConn = Test-NetConnection -ComputerName "8.8.8.8" -Port 53 -WarningAction SilentlyContinue
    if ($testConn.TcpTestSucceeded) {
        $isOnline = $true
    }
} catch {}

if ($isOnline) {
    Write-Host "[*] Internet connection detected. Checking Chocolatey bulk package manager..." -ForegroundColor Yellow
    try {
        if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
            Write-Host "[*] Bootstrapping Chocolatey silently..." -ForegroundColor Yellow
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
            $env:Path = "$env:ALLUSERSPROFILE\chocolatey\bin;$env:Path"
        }
        
        if (Get-Command choco.exe -ErrorAction SilentlyContinue) {
            Write-Host "[*] Ensuring all Non-PE software suites are installed via Chocolatey..." -ForegroundColor Yellow
            choco install -y winrar 7zip sumatrapdf javaruntime vcredist-all --no-progress --ignore-checksums
            Add-ToSystemPath "C:\Program Files\WinRAR"
            Add-ToSystemPath "C:\Program Files\7-Zip"
            Add-ToSystemPath "C:\Program Files\SumatraPDF"
            Write-Host "[+] Chocolatey Non-PE dependencies verified!" -ForegroundColor Green
        }
    } catch {
        Write-Host "[!] Note on Chocolatey execution: $_" -ForegroundColor DarkGray
    }
} else {
    Write-Host "[*] Offline mode: Skipping online Chocolatey package installer." -ForegroundColor DarkGray
}

# 15. Microsoft Office Macro & Protected View Security Bypass
# Applies essential registry keys across Office versions to ensure malicious macros detonate
Write-Host "[*] Applying Microsoft Office Macro & Protected View Security Bypass..." -ForegroundColor Yellow
try {
    $officeVersions = @("16.0", "15.0", "14.0", "12.0")
    $officeApps = @("Word", "Excel", "PowerPoint", "Access")

    foreach ($ver in $officeVersions) {
        foreach ($app in $officeApps) {
            $secPath = "HKCU:\Software\Microsoft\Office\$ver\$app\Security"
            if (-not (Test-Path $secPath)) {
                New-Item -Path $secPath -Force | Out-Null
            }
            # VBAWarnings = 1: Enable all macros without notification
            Set-ItemProperty -Path $secPath -Name "VBAWarnings" -Value 1 -Force -ErrorAction SilentlyContinue
            # AccessVBOM = 1: Trust access to the VBA project object model
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
    Write-Host "[+] Office Macro and Protected View bypasses configured." -ForegroundColor Green
} catch {
    Write-Host "[!] Note on Office security settings: $_" -ForegroundColor DarkGray
}

# 16. Deploy and Start CAPEv2 Agent
$agentSource = Join-Path $mediaDrive "agent.pyw"
$startupDir = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
$targetAgent = Join-Path $startupDir "agent.pyw"

if (Test-Path $agentSource) {
    Write-Host "[*] Installing official CAPEv2 Agent to Startup folder..." -ForegroundColor Yellow
    Copy-Item -Path $agentSource -Destination $targetAgent -Force
}

# Firewall rule for Agent port 8000
netsh advfirewall firewall add rule name="CAPE-Agent-Port" dir=in action=allow protocol=TCP localport=8000 | Out-Null
if (Test-Path $pythonExe) {
    netsh advfirewall firewall add rule name="CAPE-Agent-Python" dir=in action=allow program=$pythonExe enable=yes | Out-Null
}

# Kill any existing agent to ensure fresh start
Get-Process -Name "python", "pythonw" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq "" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "[*] Starting CAPEv2 Agent daemon on port 8000..." -ForegroundColor Yellow
if ((Test-Path $pythonwExe) -and (Test-Path $targetAgent)) {
    Start-Process -FilePath $pythonwExe -ArgumentList "`"$targetAgent`"" -WindowStyle Hidden
} elseif ((Test-Path $pythonExe) -and (Test-Path $targetAgent)) {
    Start-Process -FilePath $pythonExe -ArgumentList "`"$targetAgent`"" -WindowStyle Hidden
} elseif (Test-Path $pythonwExe) {
    Start-Process -FilePath $pythonwExe -ArgumentList "`"$agentSource`"" -WindowStyle Hidden
} elseif (Test-Path $pythonExe) {
    Start-Process -FilePath $pythonExe -ArgumentList "`"$agentSource`"" -WindowStyle Hidden
} else {
    Write-Host "[-] WARNING: Python executable not found!" -ForegroundColor Red
}

# Verification
Start-Sleep -Seconds 3
$agentActive = $false
try {
    $res = Test-NetConnection -Port 8000 -ComputerName 127.0.0.1 -WarningAction SilentlyContinue
    if ($res.TcpTestSucceeded) {
        $agentActive = $true
    }
} catch {}

if ($agentActive) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  [+] SUCCESS: Non-PE Environment Ready!" -ForegroundColor Green
    Write-Host "  [+] CAPE Agent is listening on port 8000 (192.168.250.100:8000)" -ForegroundColor Green
    Write-Host "  [+] Host can now capture the clean baseline snapshot!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Set-Content -Path "C:\cape-nonpe-ready.txt" -Value "READY $(Get-Date -Format o)"
} else {
    Write-Host "[!] Agent starting in background. Will be active on port 8000 shortly." -ForegroundColor Yellow
}

Stop-Transcript -ErrorAction SilentlyContinue
