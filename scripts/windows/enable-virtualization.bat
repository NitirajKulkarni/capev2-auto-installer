@echo off
setlocal EnableDelayedExpansion
call "%~dp0..\..\enable-windows-virtualization.bat" %*
exit /b %errorlevel%
