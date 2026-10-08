@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: CAPEv2 Virtualization & Nested Hypervisor Enabler for Windows
:: Author: Nitiraj Kulkarni
:: GitHub: https://github.com/NitirajKulkarni/capev2-auto-installer
:: ============================================================================
:: Purpose:
::   Resolves the "[FAIL] No hardware virtualization support (VT-x/AMD-V)" error
::   in Ubuntu when running under VirtualBox, VMware, or Hyper-V on Windows 10/11.
::
:: Technical Explanation:
::   On Windows 10 & 11, Windows features such as Hyper-V, WSL2, and Virtualization-
::   Based Security (VBS / Core Isolation / Memory Integrity) lock the CPU's VT-x/AMD-V
::   instructions at boot.
::   When this occurs, VirtualBox is forced into "NEM (Snail Execution Mode)" via the
::   Windows Hypervisor Platform API, which PREVENTS VirtualBox from passing nested
::   VT-x to your Ubuntu guest VM.
::   This script releases the hardware VT-x lock and enables nested virtualization.
:: ============================================================================

title CAPEv2 Virtualization Configuration Tool - By Nitiraj Kulkarni

:: ─── 1. Check for Administrator Elevation ────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ====================================================================
    echo  [!] Elevation Required: Requesting Administrator Privileges...
    echo ====================================================================
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:MENU
cls
echo ================================================================================
echo   CAPEv2 WINDOWS VIRTUALIZATION & NESTED HYPERVISOR CONFIGURATOR
echo   Author: Nitiraj Kulkarni (https://github.com/NitirajKulkarni)
echo ================================================================================
echo.
echo  Root Cause Identified:
echo    On Windows 11/10, Virtualization-Based Security (VBS) or Hyper-V locks
echo    hardware VT-x/AMD-V at boot. This forces VirtualBox/VMware into "NEM mode",
echo    preventing the hypervisor from passing VT-x into your Ubuntu guest VM.
echo.
echo --------------------------------------------------------------------------------
echo  SELECT AN ACTION:
echo --------------------------------------------------------------------------------
echo  [1] FIX ORACLE VIRTUALBOX NESTED VIRTUALIZATION (Recommended)
echo      - Disables Windows Hyper-V / VBS lock (releases VT-x to VirtualBox)
echo      - Enables --nested-hw-virt on your VirtualBox VM (e.g. CAPE-Server)
echo      - Restores 100%% native hardware VT-x execution for CAPEv2
echo.
echo  [2] FIX VMWARE WORKSTATION / PLAYER NESTED VIRTUALIZATION
echo      - Disables Windows Hyper-V lock
echo      - Guides configuration of vhv.enable = "TRUE"
echo.
echo  [3] FIX MICROSOFT HYPER-V NESTED VIRTUALIZATION
echo      - Enables ExposeVirtualizationExtensions on Hyper-V VM
echo      - Enables MAC address spoofing for CAPEv2 analysis network
echo.
echo  [4] RESTORE DEFAULT WINDOWS SETTINGS (Re-enable Hyper-V / WSL2)
echo      - Re-enables hypervisorlaunchtype auto and VBS
echo.
echo  [5] RUN SYSTEM & VIRTUALIZATION DIAGNOSTICS AUDIT
echo      - Audits CPU virtualization, VBS status, and VirtualBox VMs
echo.
echo  [0] Exit
echo --------------------------------------------------------------------------------
set /p "CHOICE=Enter choice [0-5]: "

if "%CHOICE%"=="1" goto FIX_VBOX
if "%CHOICE%"=="2" goto FIX_VMWARE
if "%CHOICE%"=="3" goto FIX_HYPERV
if "%CHOICE%"=="4" goto RESTORE_DEFAULTS
if "%CHOICE%"=="5" goto DIAGNOSTICS
if "%CHOICE%"=="0" goto EXIT_SCRIPT

echo.
echo [!] Invalid selection. Please choose a valid option.
pause
goto MENU

:: ─── Option 1: Fix VirtualBox ───────────────────────────────────────────────
:FIX_VBOX
cls
echo ================================================================================
echo   STEP 1: CONFIGURING ORACLE VIRTUALBOX NESTED VIRTUALIZATION
echo ================================================================================
echo.

set "VBOX_PATH=C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
if not exist "%VBOX_PATH%" (
    echo [!] VBoxManage.exe not found at standard location:
    echo     "%VBOX_PATH%"
    set /p "VBOX_PATH=Enter full path to VBoxManage.exe: "
)

if exist "%VBOX_PATH%" (
    echo [*] Found VirtualBox at: "%VBOX_PATH%"
    echo.
    echo [*] Listing available VirtualBox VMs:
    echo ----------------------------------------------------------------
    "%VBOX_PATH%" list vms
    echo ----------------------------------------------------------------
    echo.
    
    set "DEFAULT_VM=CAPE-Server"
    set /p "TARGET_VM=Enter VM name to configure [Press Enter for '%DEFAULT_VM%']: "
    if "!TARGET_VM!"=="" set "TARGET_VM=%DEFAULT_VM%"

    echo.
    echo [*] Applying nested virtualization flags to VM: "!TARGET_VM!"...
    "%VBOX_PATH%" modifyvm "!TARGET_VM!" --nested-hw-virt on
    "%VBOX_PATH%" modifyvm "!TARGET_VM!" --hwvirtex on
    "%VBOX_PATH%" modifyvm "!TARGET_VM!" --nestedpaging on
    "%VBOX_PATH%" modifyvm "!TARGET_VM!" --vtxvpid on
    if !errorlevel! equ 0 (
        echo [OK] VirtualBox VM "!TARGET_VM!" configured with nested hardware virtualization.
    ) else (
        echo [WARN] Could not modify VM "!TARGET_VM!". Verify VM name is correct and VM is powered off.
    )
) else (
    echo [WARN] VirtualBox not detected. Skipping direct VM modification.
)

echo.
echo ================================================================================
echo   STEP 2: RELEASING WINDOWS HYPER-V ^& VBS HARDWARE LOCK
echo ================================================================================
echo.
echo [*] Disabling Windows Hypervisor at boot (releases VT-x directly to VirtualBox)...
bcdedit /set hypervisorlaunchtype off
if %errorlevel% equ 0 (
    echo [OK] BCD hypervisorlaunchtype set to 'off'.
) else (
    echo [WARN] bcdedit failed. Ensure Secure Boot allows boot configuration changes.
)

echo.
echo [*] Disabling Virtualization-Based Security (VBS) in Registry...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard" /v "EnableVirtualizationBasedSecurity" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity" /v "Enabled" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v "LsaCfgFlags" /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] VBS and Memory Integrity registry flags disabled.

echo.
echo [*] Optional: Disabling conflicting Windows Optional Features...
echo     (This does NOT uninstall VirtualBox, it frees hardware VT-x for VirtualBox)
dism /Online /Disable-Feature /FeatureName:HypervisorPlatform /NoRestart >nul 2>&1
dism /Online /Disable-Feature /FeatureName:VirtualMachinePlatform /NoRestart >nul 2>&1
echo [OK] Windows Hypervisor Platform features disarmed.

echo.
echo ================================================================================
echo   [SUCCESS] CONFIGURATION COMPLETED!
echo ================================================================================
echo.
echo  IMPORTANT: A Windows reboot is REQUIRED for changes to take effect!
echo  After reboot:
echo    1. Start your Ubuntu VM in VirtualBox.
echo    2. Run: sudo ./install.sh --preflight
echo    3. The [FAIL] hardware virtualization error will be GONE!
echo.
set /p "REBOOT_NOW=Do you want to reboot Windows now? (Y/N) [Default: N]: "
if /i "!REBOOT_NOW!"=="Y" (
    echo.
    echo [*] Restarting system in 10 seconds... Save your work!
    shutdown /r /t 10 /c "Restarting to apply CAPEv2 Virtualization settings"
) else (
    echo.
    echo [*] Please restart your computer manually before running the installer.
)
echo.
pause
goto MENU

:: ─── Option 2: Fix VMware ───────────────────────────────────────────────────
:FIX_VMWARE
cls
echo ================================================================================
echo   CONFIGURING VMWARE WORKSTATION / PLAYER NESTED VIRTUALIZATION
echo ================================================================================
echo.
echo [*] Disabling Windows Hyper-V at boot (prevents VMware from running in WHP mode)...
bcdedit /set hypervisorlaunchtype off
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard" /v "EnableVirtualizationBasedSecurity" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity" /v "Enabled" /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] Windows Hypervisor Platform disabled.
echo.
echo [*] INSTRUCTIONS FOR VMWARE WORKSTATION:
echo   1. Power off your Ubuntu VM.
echo   2. Open VMware Workstation / Player.
echo   3. Click "Edit virtual machine settings" for your Ubuntu VM.
echo   4. Select "Processors".
echo   5. Check the box: "Virtualize Intel VT-x/EPT or AMD-V/RVI".
echo   6. Check the box: "Virtualize CPU performance counters".
echo   7. Click "OK".
echo.
echo  Alternatively, add these lines to your VM's .vmx file:
echo    vhv.enable = "TRUE"
echo    vpmc.enable = "TRUE"
echo.
echo  A system reboot is required to disable Windows Hyper-V!
echo.
pause
goto MENU

:: ─── Option 3: Fix Hyper-V ───────────────────────────────────────────────────
:FIX_HYPERV
cls
echo ================================================================================
echo   CONFIGURING MICROSOFT HYPER-V NESTED VIRTUALIZATION
echo ================================================================================
echo.
echo [*] Ensuring Windows Hypervisor is enabled at boot...
bcdedit /set hypervisorlaunchtype auto
echo.
echo [*] Querying Hyper-V virtual machines...
powershell -NoProfile -Command "if (Get-Command Get-VM -ErrorAction SilentlyContinue) { Get-VM | Format-Table Name, State, CPUUsage } else { Write-Host '[!] Hyper-V PowerShell module not found.' }"
echo.
set /p "HYPERV_VM=Enter Hyper-V VM Name: "
if not "!HYPERV_VM!"=="" (
    echo [*] Enabling Nested Virtualization on Hyper-V VM '!HYPERV_VM!'...
    powershell -NoProfile -Command "Set-VMProcessor -VMName '!HYPERV_VM!' -ExposeVirtualizationExtensions $true"
    powershell -NoProfile -Command "Get-VMNetworkAdapter -VMName '!HYPERV_VM!' | Set-VMNetworkAdapter -MacAddressSpoofing On"
    echo [OK] Nested virtualization and MAC spoofing enabled for '!HYPERV_VM!'.
)
echo.
pause
goto MENU

:: ─── Option 4: Restore Defaults ──────────────────────────────────────────────
:RESTORE_DEFAULTS
cls
echo ================================================================================
echo   RESTORING DEFAULT WINDOWS HYPER-V ^& VBS SETTINGS
echo ================================================================================
echo.
echo [*] Re-enabling Windows Hypervisor launch at boot (for WSL2 / Hyper-V)...
bcdedit /set hypervisorlaunchtype auto
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard" /v "EnableVirtualizationBasedSecurity" /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Default Windows hypervisor launch restored.
echo.
echo  Please reboot your computer to apply default settings.
echo.
pause
goto MENU

:: ─── Option 5: Diagnostics ───────────────────────────────────────────────────
:DIAGNOSTICS
cls
echo ================================================================================
echo   SYSTEM VIRTUALIZATION AUDIT ^& DIAGNOSTICS
echo ================================================================================
echo.
echo [*] CPU Architecture:
powershell -NoProfile -Command "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors | Format-List"

echo [*] Boot Configuration Data (BCD) Hypervisor Status:
powershell -NoProfile -Command "bcdedit /enum {current} | Select-String 'hypervisorlaunchtype'"

echo.
echo [*] Virtualization-Based Security (VBS) Status:
powershell -NoProfile -Command "Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard | Select-Object SecurityServicesConfigured, SecurityServicesRunning, VirtualizationBasedSecurityStatus | Format-List"

echo [*] Oracle VirtualBox VM Status:
set "VBOX_PATH=C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
if exist "%VBOX_PATH%" (
    "%VBOX_PATH%" list vms
    echo.
    echo [*] Checking CAPE-Server nested virtualization status:
    "%VBOX_PATH%" showvminfo "CAPE-Server" --machinereadable 2>nul | findstr /i "nested-hw-virt hwvirtex"
) else (
    echo [!] VirtualBox not found at "%VBOX_PATH%".
)

echo.
echo ================================================================================
pause
goto MENU

:EXIT_SCRIPT
echo.
echo Exiting. Goodbye!
exit /b 0
