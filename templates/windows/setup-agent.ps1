# CAPEv2 Windows Guest Provisioning and Agent Bootstrap Script
# Run inside the Windows Guest to prepare baseline and start CAPE Agent.

$ErrorActionPreference = "Continue"

Write-Output "[*] Configuring Windows Guest for CAPEv2 Sandbox..."

# Disable Windows Defender Realtime Monitoring (standard for sandbox analysis)
try {
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableIOAVProtection $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableScriptScanning $true -ErrorAction SilentlyContinue
} catch {
    Write-Output "[!] Note: Could not adjust Defender settings: $_"
}

# Disable UAC
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "EnableLUA" -Value 0 -Force

# Disable Windows Updates
Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
Set-Service -Name wuauserv -StartupType Disabled -ErrorAction SilentlyContinue

# Disable Windows Firewall for sandbox analysis interface
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False

# Configure static IP if required
# $interfaceName = (Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1).Name
# New-NetIPAddress -InterfaceAlias $interfaceName -IPAddress "192.168.250.100" -PrefixLength 24 -DefaultGateway "192.168.250.1"

# Create startup shortcut for CAPE agent
$agentPath = "C:\agent\agent.py"
$pythonPath = "C:\Python310\python.exe"
if (Test-Path $agentPath) {
    Write-Output "[*] Registering CAPE agent startup..."
    $startupFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
    $shortcutPath = Join-Path $startupFolder "cape-agent.lnk"
    $wscriptShell = New-Object -ComObject WScript.Shell
    $shortcut = $wscriptShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonPath
    $shortcut.Arguments = "$agentPath"
    $shortcut.WindowStyle = 7 # Minimized
    $shortcut.Save()
}

Write-Output "[+] Guest configuration complete. Ready for snapshot."
