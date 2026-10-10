# CAPEv2 Windows Guest Provisioning and Agent Bootstrap Script
# Run automatically inside the Windows Guest on first boot to prepare baseline and start CAPE Agent.

$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\cape-setup.log" -Append -ErrorAction SilentlyContinue

Write-Output "[*] Configuring Windows Guest for CAPEv2 Sandbox..."

# 1. Network Configuration: configure static IP on analysis interface
try {
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1
    if (-not $adapter) {
        $adapter = Get-NetAdapter | Select-Object -First 1
    }
    if ($adapter) {
        Write-Output "[*] Configuring static IP 192.168.250.100 on adapter '$($adapter.Name)'..."
        Remove-NetIPAddress -InterfaceIndex $adapter.ifIndex -Confirm:$false -ErrorAction SilentlyContinue
        Remove-NetRoute -InterfaceIndex $adapter.ifIndex -Confirm:$false -ErrorAction SilentlyContinue
        New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress "192.168.250.100" -PrefixLength 24 -DefaultGateway "192.168.250.1" -ErrorAction SilentlyContinue
        Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ("8.8.8.8", "1.1.1.1") -ErrorAction SilentlyContinue
    }
} catch {
    Write-Output "[!] Note on network configuration: $_"
}

# 2. Disable Windows Defender (standard for malware sandbox baseline)
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
} catch {
    Write-Output "[!] Note on Defender settings: $_"
}

# 3. Disable UAC (User Account Control)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "EnableLUA" -Value 0 -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "ConsentPromptBehaviorAdmin" -Value 0 -Force -ErrorAction SilentlyContinue

# 4. Disable Windows Updates
Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
Set-Service -Name wuauserv -StartupType Disabled -ErrorAction SilentlyContinue

# 5. Disable Windows Firewall
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False -ErrorAction SilentlyContinue

# 6. Disable Sleep, Screen Timeout & Hibernation
powercfg -x -standby-timeout-ac 0
powercfg -x -hibernate-timeout-ac 0
powercfg -x -monitor-timeout-ac 0

# 7. Install Python and CAPE Agent from the Unattended ISO
Write-Output "[*] Locating installation media..."
$isoDrive = (Get-PSDrive -PSProvider FileSystem | Where-Object { Test-Path (Join-Path $_.Root "python-installer.exe") }).Root
if (-not $isoDrive) {
    Write-Output "[-] ERROR: Could not find python-installer.exe on any CD-ROM drive!"
    exit 1
}

$pythonInstaller = Join-Path $isoDrive "python-installer.exe"
$agentSource = Join-Path $isoDrive "agent.pyw"

Write-Output "[*] Installing Python 3.10 silently (this may take a minute)..."
$proc = Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Output "[-] WARNING: Python installation returned exit code $($proc.ExitCode)"
}

Write-Output "[*] Installing official CAPEv2 Agent to Startup folder..."
$startupDir = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
Copy-Item -Path $agentSource -Destination (Join-Path $startupDir "agent.pyw") -Force

Write-Output "[*] Allowing Python through Windows Firewall..."
netsh advfirewall firewall add rule name="CAPE-Agent-Python" dir=in action=allow program="C:\Program Files\Python310\python.exe" enable=yes | Out-Null
netsh advfirewall firewall add rule name="CAPE-Agent-Port" dir=in action=allow protocol=TCP localport=8000 | Out-Null

Write-Output "[*] Starting CAPEv2 Agent in the background..."
$pythonPath = "C:\Program Files\Python310\pythonw.exe"
if (Test-Path $pythonPath) {
    Start-Process -FilePath $pythonPath -ArgumentList (Join-Path $startupDir "agent.pyw") -WindowStyle Hidden
} else {
    Write-Output "[-] WARNING: pythonw.exe not found! Agent will start on next reboot."
}

Write-Output "[+] Guest configuration complete! Real CAPE agent is installed."

Stop-Transcript -ErrorAction SilentlyContinue
