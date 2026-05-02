@echo off
REM ===================================================================
REM Welcome.bat - Passport to Wealth Finance Clarity bootstrap installer
REM
REM v0 SKELETON for Windows - mirrors the macOS Welcome.command flow.
REM Real package installs are stubbed. See engagement/development/finance-clarity-build-spec.md
REM for the full intended behavior.
REM
REM Best practice: this batch wrapper just bootstraps PowerShell, where
REM the real install logic lives (Welcome.ps1). Batch is brittle for
REM anything beyond hello-world; PowerShell is what Windows users get
REM real installer behavior from.
REM
REM Copyright (c) 2026 Passport to Wealth. All rights reserved.
REM ===================================================================

setlocal

title Setting up your finance workspace

REM Re-launch ourselves under PowerShell with execution policy bypass for
REM this single process only. We do NOT change the system-wide policy.
set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%Welcome.ps1"

if not exist "%PS_SCRIPT%" (
  echo.
  echo ERROR: Welcome.ps1 not found next to Welcome.bat.
  echo This installer is incomplete. Please contact your advisor.
  echo.
  pause
  exit /b 1
)

REM Hand off to PowerShell. -NoProfile keeps user dotfiles from interfering.
REM -ExecutionPolicy Bypass applies to this process only.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

set "PS_EXIT=%ERRORLEVEL%"

if %PS_EXIT% NEQ 0 (
  echo.
  echo Setup did not complete. See the log file your installer mentioned.
  echo Press any key to close this window.
  pause >nul
)

exit /b %PS_EXIT%
