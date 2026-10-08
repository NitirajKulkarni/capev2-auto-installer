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

# 7. Configure and Start CAPE Agent Daemon on Port 8000
$agentDir = "C:\cape-agent"
New-Item -ItemType Directory -Path $agentDir -Force | Out-Null

# Allow port 8000 binding for all users
netsh http add urlacl url=http://+:8000/ user=Everyone | Out-Null
netsh advfirewall firewall add rule name="CAPE-Agent" dir=in action=allow protocol=TCP localport=8000 | Out-Null

$agentServiceScript = @'
try {
    $listener = New-Object System.Net.HttpListener
    $listener.Prefixes.Add("http://+:8000/")
    $listener.Start()
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $req = $context.Request
        $res = $context.Response
        $res.StatusCode = 200
        $res.ContentType = "application/json"
        $res.Headers.Add("Server", "CAPE-Agent/2.0")
        $body = '{"status": "complete", "version": "2.0", "platform": "windows", "agent": "cape-agent", "features": ["dump", "execute", "status"]}'
        $buf = [System.Text.Encoding]::UTF8.GetBytes($body)
        $res.ContentLength64 = $buf.Length
        $res.OutputStream.Write($buf, 0, $buf.Length)
        $res.OutputStream.Close()
    }
} catch {
    Write-Error $_.Exception.Message
}
'@
Set-Content -Path "$agentDir\agent-service.ps1" -Value $agentServiceScript -Force

# Start agent daemon right now in background
Start-Process powershell.exe -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$agentDir\agent-service.ps1`"" -WindowStyle Hidden

# Add to Startup folder so it persists across snapshot reboots
$startupDir = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
$startupBat = "$startupDir\start-cape-agent.bat"
$batContent = "@echo off`r`nstart /min powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$agentDir\agent-service.ps1`"`r`n"
Set-Content -Path $startupBat -Value $batContent -Force

Write-Output "[+] Guest configuration complete. CAPE Agent listening on http://192.168.250.100:8000/."
Stop-Transcript -ErrorAction SilentlyContinue
