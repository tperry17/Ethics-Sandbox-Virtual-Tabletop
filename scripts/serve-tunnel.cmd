@echo off
rem Start scripts\serve-tunnel.ps1 whatever Windows' PowerShell script policy
rem is. Options pass through: scripts\serve-tunnel -SkipChecks
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve-tunnel.ps1" %*
