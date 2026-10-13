# CAPEv2 Windows Guest Non-PE Environment Enabler & Baseline Preparation
# Configures Windows guest to analyze all Non-PE formats (PowerShell, Batch, VBS, JS, PDF, Office, Archives)
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

    # Disable Open File Security Warnings for downloaded scripts
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Associations" /v "DefaultFileTypeRisk" /t REG_DWORD /d 1806 /f | Out-Null
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Associations" /v "LowRiskFileTypes" /t REG_SZ /d ".exe;.bat;.cmd;.ps1;.vbs;.js;.wsf;.hta;.pdf;.zip;.rar;.7z;" /f | Out-Null
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

# 8. Install 7-Zip silently (for Archive extraction: .zip, .rar, .7z, .iso)
$sevenZipInstaller = Get-ChildItem -Path $mediaDrive -Filter "7z*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($sevenZipInstaller) {
    Write-Host "[*] Installing 7-Zip silently from $($sevenZipInstaller.FullName)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $sevenZipInstaller.FullName -ArgumentList "/S" -Wait -PassThru
    if ($p.ExitCode -eq 0 -or (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
        Write-Host "[+] 7-Zip installed successfully at C:\Program Files\7-Zip\7z.exe" -ForegroundColor Green
        # Add to System PATH
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        if ($currentPath -notlike "*7-Zip*") {
            [Environment]::SetEnvironmentVariable("Path", "$currentPath;C:\Program Files\7-Zip", "Machine")
        }
    }
} else {
    Write-Host "[!] 7-Zip installer not found on media drive. Skipping 7-Zip." -ForegroundColor DarkGray
}

# 9. Install PDF Reader silently (for PDF analysis: .pdf)
$pdfInstaller = Get-ChildItem -Path $mediaDrive -Filter "*SumatraPDF*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pdfInstaller) {
    $pdfInstaller = Get-ChildItem -Path $mediaDrive -Filter "*pdf*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($pdfInstaller -and (Get-Item $pdfInstaller.FullName).Length -gt 1048576) {
    try {
        Write-Host "[*] Installing PDF Reader silently from $($pdfInstaller.FullName)..." -ForegroundColor Yellow
        $p = Start-Process -FilePath $pdfInstaller.FullName -ArgumentList "-s -all-users" -Wait -PassThru
        if ($p.ExitCode -eq 0) {
            Write-Host "[+] PDF Reader installed successfully!" -ForegroundColor Green
        }
    } catch {
        Write-Host "[!] Note on PDF installer execution: $_" -ForegroundColor DarkGray
    }
} else {
    Write-Host "[*] Using Windows default PDF handler (Edge)..." -ForegroundColor Yellow
}

# 10. Install Python 3.10 if not already present
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

# 11. Deploy and Start CAPEv2 Agent
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
