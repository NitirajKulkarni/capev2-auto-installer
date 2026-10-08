@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: CAPEv2 Virtualization & Nested Hypervisor Enabler for Windows
:: Author: Nitiraj Kulkarni
:: GitHub: https://github.com/NitirajKulkarni/capev2-auto-installer
:: ============================================================================
:: Purpose:
::   Resolves "[FAIL] No hardware virtualization support (VT-x/AMD-V)" in Ubuntu
::   when running under Oracle VirtualBox, VMware, or Hyper-V on Windows 10/11.
::
:: Technical Background:
::   On Windows 10 and 11, background security features like Virtualization-Based
::   Security (VBS / Core Isolation / Memory Integrity) and Hyper-V lock the CPU's
::   hardware VT-x/AMD-V instructions at boot.
::   This forces VirtualBox into "NEM (Snail Execution Mode)", which PREVENTS
::   VirtualBox from passing nested VT-x instructions into the Ubuntu guest VM.
::   This utility releases the CPU hardware lock, configures hypervisor flags,
::   and enables true nested hardware virtualization.
:: ============================================================================

title CAPEv2 Windows Virtualization Configurator - By Nitiraj Kulkarni

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

:: Ensure VBOX_USER_HOME is set to current user's profile to prevent profile mismatch under elevation
if not defined VBOX_USER_HOME (
    if exist "%USERPROFILE%\.VirtualBox" set "VBOX_USER_HOME=%USERPROFILE%\.VirtualBox"
)

:MENU
cls
echo ================================================================================
echo   CAPEv2 WINDOWS VIRTUALIZATION & NESTED HYPERVISOR CONFIGURATOR
echo   Author: Nitiraj Kulkarni (https://github.com/NitirajKulkarni)
echo ================================================================================
echo.
echo  Root Cause:
echo    On Windows 10/11, Virtualization-Based Security (VBS) or Hyper-V locks
echo    CPU VT-x/AMD-V at boot. This forces VirtualBox/VMware into "NEM mode",
echo    preventing the hypervisor from passing VT-x into your Ubuntu guest VM.
echo.
echo --------------------------------------------------------------------------------
echo  SELECT AN ACTION:
echo --------------------------------------------------------------------------------
echo  [1] FIX ORACLE VIRTUALBOX NESTED VIRTUALIZATION (Recommended)
echo      - Automatically discovers your VirtualBox VMs and .vbox configuration files
echo      - Applies --nested-hw-virt, --hwvirtex, --nestedpaging, and --vtxvpid
echo      - Disables Windows Hyper-V and VBS hardware lock at boot
echo      - Restores 100%% native hardware VT-x execution for CAPEv2
echo.
echo  [2] FIX VMWARE WORKSTATION / PLAYER NESTED VIRTUALIZATION
echo      - Disables Windows Hyper-V lock (prevents VMware running in WHP mode)
echo      - Configures vhv.enable = "TRUE" guidance
echo.
echo  [3] FIX MICROSOFT HYPER-V NESTED VIRTUALIZATION
echo      - Enables ExposeVirtualizationExtensions on Hyper-V VM
echo      - Enables MAC address spoofing for CAPEv2 analysis bridge
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

:: Locate VBoxManage
set "VBOX_PATH="
if exist "%ProgramFiles%\Oracle\VirtualBox\VBoxManage.exe" (
    set "VBOX_PATH=%ProgramFiles%\Oracle\VirtualBox\VBoxManage.exe"
) else if exist "%ProgramFiles(x86)%\Oracle\VirtualBox\VBoxManage.exe" (
    set "VBOX_PATH=%ProgramFiles(x86)%\Oracle\VirtualBox\VBoxManage.exe"
)

if not defined VBOX_PATH (
    echo [!] VBoxManage.exe not found at standard installation paths.
    set /p "VBOX_PATH=Enter full path to VBoxManage.exe: "
)

if not exist "!VBOX_PATH!" (
    echo [WARN] VirtualBox executable not accessible. Proceeding to Windows Hyper-V fix...
    goto VBOX_WINDOWS_FIX
)

echo [*] Found VirtualBox at: "!VBOX_PATH!"

:: Check if VirtualBox is running and close cleanly to avoid file locks
echo.
echo [*] Checking for active VirtualBox processes...
tasklist /FI "IMAGENAME eq VirtualBox.exe" 2>nul | find /I /N "VirtualBox.exe">nul
if "%ERRORLEVEL%"=="0" (
    echo [!] VirtualBox is currently running. Closing VirtualBox to save changes...
    taskkill /F /IM VirtualBox.exe >nul 2>&1
    taskkill /F /IM VBoxSVC.exe >nul 2>&1
    timeout /t 2 >nul
    echo [OK] VirtualBox closed.
) else (
    echo [OK] VirtualBox is not currently running.
)

:: Display discovered VMs
echo.
echo [*] Discovered VirtualBox Virtual Machines:
echo ----------------------------------------------------------------
set "FOUND_VMS=0"
for /f "tokens=1,* delims= " %%A in ('^""!VBOX_PATH!" list vms 2^>nul^"') do (
    echo   %%A %%B
    set /a FOUND_VMS+=1
)
if "!FOUND_VMS!"=="0" (
    echo   (No registered VMs found under current profile. Searching disk...)
    if exist "%USERPROFILE%\VirtualBox VMs" (
        for /d %%D in ("%USERPROFILE%\VirtualBox VMs\*") do (
            if exist "%%~D\%%~nxD.vbox" (
                echo   "%%~nxD" [Found on disk: %%~D]
                set /a FOUND_VMS+=1
            )
        )
    )
)
echo ----------------------------------------------------------------
echo.

set /p "TARGET_VM=Enter VM name to configure (or type ALL to configure all): "
if "!TARGET_VM!"=="" (
    echo [!] No VM name entered. Please specify a VM name.
    pause
    goto FIX_VBOX
)

:: Function to apply flags to a given VM or .vbox file
if /i "!TARGET_VM!"=="ALL" (
    echo.
    echo [*] Applying nested virtualization flags to ALL detected VMs...
    for /d %%D in ("%USERPROFILE%\VirtualBox VMs\*") do (
        if exist "%%~D\%%~nxD.vbox" (
            echo   -> Configuring: "%%~nxD"
            call :APPLY_VBOX_FLAGS "!VBOX_PATH!" "%%~D\%%~nxD.vbox" "%%~nxD"
        )
    )
) else (
    echo.
    echo [*] Applying nested virtualization flags to: "!TARGET_VM!"...
    set "DIRECT_VBOX=%USERPROFILE%\VirtualBox VMs\!TARGET_VM!\!TARGET_VM!.vbox"
    if exist "!DIRECT_VBOX!" (
        call :APPLY_VBOX_FLAGS "!VBOX_PATH!" "!DIRECT_VBOX!" "!TARGET_VM!"
    ) else (
        call :APPLY_VBOX_FLAGS "!VBOX_PATH!" "!TARGET_VM!" "!TARGET_VM!"
    )
)

:VBOX_WINDOWS_FIX
echo.
echo ================================================================================
echo   STEP 2: RELEASING WINDOWS HYPER-V ^& VBS HARDWARE VT-X LOCK
echo ================================================================================
echo.
echo [*] Disabling Windows Hypervisor launch at boot (releases VT-x directly to VirtualBox)...
bcdedit /set hypervisorlaunchtype off
if %errorlevel% equ 0 (
    echo [OK] BCD hypervisorlaunchtype set to 'off'.
) else (
    echo [WARN] bcdedit returned non-zero. Ensure Secure Boot allows boot configuration.
)

echo.
echo [*] Disabling Virtualization-Based Security (VBS) in Registry...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard" /v "EnableVirtualizationBasedSecurity" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard" /v "RequirePlatformSecurityFeatures" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity" /v "Enabled" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity" /v "WasEnabledBy" /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v "LsaCfgFlags" /t REG_DWORD /d 0 /f >nul 2>&1
echo [OK] VBS and Memory Integrity (HVCI) registry flags disabled.

echo.
echo [*] Disabling Windows Hypervisor Platform features...
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
echo    2. In Ubuntu terminal, run: sudo ./install.sh --preflight
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

:: Subroutine to apply VirtualBox flags safely
:APPLY_VBOX_FLAGS
set "EXE=%~1"
set "TARGET=%~2"
set "LABEL=%~3"

"%EXE%" modifyvm "%TARGET%" --nested-hw-virt on 2>nul
if %errorlevel% neq 0 (
    :: Fallback: Try searching disk if target was a name and failed
    if exist "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" (
        "%EXE%" modifyvm "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" --nested-hw-virt on >nul 2>&1
        "%EXE%" modifyvm "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" --hwvirtex on >nul 2>&1
        "%EXE%" modifyvm "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" --nestedpaging on >nul 2>&1
        "%EXE%" modifyvm "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" --vtxvpid on >nul 2>&1
        "%EXE%" modifyvm "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" --vtxux on >nul 2>&1
        "%EXE%" modifyvm "%USERPROFILE%\VirtualBox VMs\%LABEL%\%LABEL%.vbox" --paravirtprovider default >nul 2>&1
        echo [OK] VirtualBox VM '%LABEL%' configured via .vbox file with nested VT-x.
        exit /b 0
    )
    echo [WARN] Could not modify VM '%LABEL%'. Verify VM name and ensure VM is powered off.
    exit /b 1
)

"%EXE%" modifyvm "%TARGET%" --hwvirtex on >nul 2>&1
"%EXE%" modifyvm "%TARGET%" --nestedpaging on >nul 2>&1
"%EXE%" modifyvm "%TARGET%" --vtxvpid on >nul 2>&1
"%EXE%" modifyvm "%TARGET%" --vtxux on >nul 2>&1
"%EXE%" modifyvm "%TARGET%" --paravirtprovider default >nul 2>&1
echo [OK] VirtualBox VM '%LABEL%' configured with nested hardware virtualization.
exit /b 0

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
