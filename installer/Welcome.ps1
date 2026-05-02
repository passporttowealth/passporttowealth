# Welcome.ps1 - Passport to Wealth Finance Clarity bootstrap installer (Windows)
#
# Run by the client after they download from https://passporttowealth.app/.
# Mirrors macOS Welcome.command step-for-step. The .bat sibling launches this
# .ps1 with -ExecutionPolicy Bypass scoped to the single process.
#
# Full design: dev/finance-clarity-build-spec.md §4. macOS reference: Welcome.command.
#
# Copyright (c) 2026 Passport to Wealth. All rights reserved.

#Requires -Version 5.1

$ErrorActionPreference = 'Stop'

# ── Helpers ────────────────────────────────────────────────────────────────────
function Write-Hr {
    Write-Host ("-" * 68) -ForegroundColor DarkGray
}
function Write-Say { param([string]$msg) Write-Host $msg }
function Write-Ok  { param([string]$msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-WarnLine { param([string]$msg) Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-FailLine { param([string]$msg) Write-Host "  X $msg" -ForegroundColor Red }

# B9.3 — pacing helpers (Mac-mirror). --Auto bypasses for CI / Rafa's reruns.
$Global:AutoMode = $false
$Global:PaceMs = 400
foreach ($a in $args) { if ($a -eq "--auto" -or $a -eq "-Auto") { $Global:AutoMode = $true; $Global:PaceMs = 0 } }

function Write-OkPaced  { param([string]$msg) Write-Ok $msg;  if (-not $Global:AutoMode) { Start-Sleep -Milliseconds $Global:PaceMs } }
function Write-SayPaced { param([string]$msg) Write-Say $msg; if (-not $Global:AutoMode) { Start-Sleep -Milliseconds $Global:PaceMs } }

# Pause-ForUser — Mac-mirror of pause_for_user. Skipped when --Auto or no host UI.
function Pause-ForUser {
    if ($Global:AutoMode) { return }
    Write-Host ""
    Read-Host "Press Enter to continue" | Out-Null
}

# Log file in the same place pattern as macOS: under user's local app data.
$LogDir  = Join-Path $env:LOCALAPPDATA "PassportToWealth\Logs"
$LogPath = Join-Path $LogDir "passport-to-wealth-install.log"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
function Write-Log {
    param([string]$msg)
    $ts = (Get-Date).ToUniversalTime().ToString("o")
    Add-Content -Path $LogPath -Value "[$ts] $msg"
}

Clear-Host
Write-Hr
Write-Host "Welcome - let's set up your private finance workspace." -ForegroundColor White
Write-Hr
Write-Say ""
Write-Say "I'll do all the technical bits. You'll only need to:"
Write-Say "  1. Allow Windows to run the installer when it asks."
Write-Say "  2. Sign in to your AI assistant."
Write-Say "  3. Sign up for the service that hosts your private dashboard."
Write-Say ""

# ── Prototype notice ──────────────────────────────────────────────────────────
Write-Say ""
Write-Hr
Write-Host "  ⚠  PROTOTYPE - pre-release software" -ForegroundColor Yellow
Write-Hr
Write-Say ""
Write-Say "This is a pilot tool for clients of Passport to Wealth, under"
Write-Say "active development. Use it as a complement to - not a replacement"
Write-Say "for - your existing financial records."
Write-Say ""
Write-Say "  - Expect bugs and incomplete features."
Write-Say "  - Always keep your original bank exports and statements."
Write-Say "  - Do not delete source files based on what the dashboard shows."
Write-Say "  - If anything looks wrong, tell your advisor - don't assume the"
Write-Say "    dashboard is correct."
Write-Say ""

# ── Anthropic data-terms consent gate (OP-13) ─────────────────────────────────
Write-Hr
Write-Host "Before we continue - about the AI assistant" -ForegroundColor White
Write-Hr
Write-Say ""
Write-Say "This workspace uses Claude, an AI assistant made by Anthropic."
Write-Say "When you ask Claude to build, refresh, or troubleshoot your dashboard,"
Write-Say "the contents of the messages you send (which may include details from"
Write-Say "your financial files as you discuss them) are sent to Anthropic to"
Write-Say "produce a response."
Write-Say ""
Write-Say "Anthropic's data handling - including what they retain, for how long,"
Write-Say "whether your conversations are used to train models, and how you can"
Write-Say "change those settings - is described in their official documentation."
Write-Say "Please review it before continuing:"
Write-Say ""
Write-Host "  - Privacy hub:           https://privacy.anthropic.com/" -ForegroundColor White
Write-Host "  - Privacy policy:        https://www.anthropic.com/legal/privacy" -ForegroundColor White
Write-Host "  - Consumer (Pro/Max):    https://www.anthropic.com/legal/consumer-terms" -ForegroundColor White
Write-Host "  - Commercial (API key):  https://www.anthropic.com/legal/commercial-terms" -ForegroundColor White
Write-Host "  - Trust & security:      https://trust.anthropic.com/" -ForegroundColor White
Write-Say ""
Write-Say "Things to know - and to manage in your Anthropic account settings:"
Write-Say "  - You can opt out of having your conversations used to improve Claude."
Write-Say "  - You can delete your conversation history at any time."
Write-Say "  - Sensitive files (paystubs, tax documents) are skipped by default by"
Write-Say "    this skill, so their contents are not sent to Claude unless you"
Write-Say "    explicitly ask."
Write-Say ""
Write-Say "If you do not accept Anthropic's terms, please stop here and contact"
Write-Say "your advisor - we can talk about alternatives."
Write-Say ""

# NOTE (B9.1): we deliberately do NOT auto-open the privacy hub here.
# Auto-opening mid-flow snaps focus away from Terminal and confuses users
# about what to type next. Windows Terminal also linkifies URLs — users
# can click if they want to read first.

Write-Say "By typing 'I accept' below you confirm:"
Write-Say "  1. You accept Anthropic's data-handling terms (linked above)."
Write-Say "  2. You understand this is prototype software and you will keep"
Write-Say "     your original financial records as the source of truth."
Write-Say ""

while ($true) {
    $consent = (Read-Host "Type 'I accept' to continue, or 'no' to cancel").Trim().ToLowerInvariant()
    switch ($consent) {
        { $_ -in @("i accept","i agree","accept","agree","yes") } {
            Write-Ok "Acceptance recorded."
            Write-Log ("consent_accepted_at=" + (Get-Date).ToUniversalTime().ToString("o") + " (anthropic_data_terms + prototype_status)")
            $consentDone = $true
            break
        }
        { $_ -in @("no","cancel","quit","stop","") } {
            Write-Say ""
            Write-Host "No problem - install cancelled. Talk to your advisor any time." -ForegroundColor DarkGray
            Write-Log "consent_declined"
            exit 0
        }
        default {
            Write-WarnLine "I didn't understand. Please type 'I accept' or 'no'."
        }
    }
    if ($consentDone) { break }
}

Write-Say ""
Read-Host "Press Enter to begin the install (or close this window to cancel)" | Out-Null

# ── Pre-flight (OP-11) ────────────────────────────────────────────────────────
Write-Say ""
Write-Hr
Write-Host "Step 1 of 6 - Checking your computer" -ForegroundColor White
Write-Hr
Write-Log "preflight start"

# Windows version (Windows 10 1903+ / Windows 11)
$os = Get-CimInstance Win32_OperatingSystem
$buildNum = [int]$os.BuildNumber
if ($buildNum -lt 18362) {
    Write-FailLine "Your Windows is too old (build $buildNum). I need Windows 10 build 18362 (1903) or later."
    Write-FailLine "FCB-0001"
    Write-Log "FCB-0001 windows_build=$buildNum"
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}
Write-OkPaced "Windows version OK (build $buildNum)"

# Free disk space on home drive
$drive = (Get-Item $env:USERPROFILE).PSDrive
$freeGB = [math]::Round($drive.Free / 1GB)
if ($freeGB -lt 5) {
    Write-FailLine "Only $freeGB GB free on your home drive. I need at least 5 GB."
    Write-FailLine "FCB-0002 - free up some space and run me again."
    Write-Log "FCB-0002 free_gb=$freeGB"
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}
Write-OkPaced "Free disk space OK ($freeGB GB)"

# MDM / Intune detection (best-effort)
$mdmEnrolled = $false
try {
    $mdm = Get-CimInstance -Namespace root\cimv2\mdm\dmmap -ClassName MDM_DevDetail_Ext01 -Filter "InstanceID='Ext' AND ParentID='./DevDetail'" -ErrorAction Stop
    if ($mdm -and $mdm.DeviceName) { $mdmEnrolled = $true }
} catch { }
if ($mdmEnrolled) {
    Write-FailLine "Your computer is managed by an organization (MDM enrolled)."
    Write-FailLine "This skill is designed for personal computers. Please talk to your advisor."
    Write-FailLine "FCB-0003"
    Write-Log "FCB-0003 mdm_detected=true"
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}
Write-OkPaced "Personal computer (not MDM-managed)"

# Network reachability
try {
    Invoke-WebRequest -Uri "https://api.frankfurter.app/latest" -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-OkPaced "Network reachable"
} catch {
    Write-WarnLine "Couldn't reach the exchange-rate service. The installer will continue but FX may be stale."
    Write-Log "FCB-0010 network_check_failed"
}

Pause-ForUser  # B9.3 — gate before tools-install section

# ── Stub: runtime / auth / publishing-host / finalize ─────────────────────────
Write-Say ""
Write-Hr
Write-Host "Step 2 of 6 - Installing the tools your dashboard needs" -ForegroundColor White
Write-Hr
Write-WarnLine "[STUB] Would install: Python 3.11, jq equivalent, openpyxl,"
Write-WarnLine "       pdfplumber, pyyaml, chardet, Claude Code CLI, the publishing-host"
Write-WarnLine "       skill, and the finance-clarity-build skill."
Write-WarnLine "       On Windows the package manager would be winget or scoop, into a"
Write-WarnLine "       per-workspace virtualenv so nothing global is touched."
Write-Log "stub: runtime install"

Write-Say ""
Write-Hr
Write-Host "Step 3 of 6 - Signing in to your AI assistant" -ForegroundColor White
Write-Hr
Write-Say ""
Write-Say "How do you sign in to Claude?"
Write-Say "  1. Claude Pro (~`$17/month) - sign in with your email"
Write-Say "  2. Claude Max - sign in with your email"
Write-Say "  3. An Anthropic API key - paste the key (starts with sk-ant-)"
Write-Say ""
Write-Host "  (If you don't have any of these, please call your advisor - this is" -ForegroundColor DarkGray
Write-Host "  the one step I can't do without you.)" -ForegroundColor DarkGray
Write-Say ""
$authChoice = (Read-Host "Type 1, 2, or 3").Trim()
switch ($authChoice) {
    { $_ -in @('1','2') } {
        Write-WarnLine "[STUB] Would launch claude to trigger the OAuth browser flow."
        Write-Log "stub: claude oauth"
    }
    '3' {
        Write-Say ""
        $sec = Read-Host "Paste your Anthropic API key (won't be shown)" -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        $apiKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
        if ($apiKey -notmatch "^sk-ant-") {
            Write-FailLine "That doesn't look like an Anthropic API key (should start with sk-ant-)."
            Write-FailLine "FCB-0004"
            Write-Log "FCB-0004 api_key_format_invalid"
            Read-Host "Press Enter to close" | Out-Null
            exit 1
        }
        Write-WarnLine "[STUB] Would write key to workspace .env (locked permissions),"
        Write-WarnLine "       export to START-HERE's launch env, and verify with a 1-token request."
        Write-Log "stub: api key path"
    }
    default {
        Write-FailLine "I didn't understand. Run me again and pick 1, 2, or 3."
        Read-Host "Press Enter to close" | Out-Null
        exit 1
    }
}
Write-OkPaced "AI assistant ready"

Pause-ForUser  # B9.3 — gate before publishing-host signup

Write-Say ""
Write-Hr
Write-Host "Step 4 of 6 - Setting up your private dashboard host" -ForegroundColor White
Write-Hr
Write-WarnLine "[STUB] Same publishing-host signup flow as macOS - opens browser,"
Write-WarnLine "       prompts for the API key, validates it, with the same"
Write-WarnLine "       paste-the-wrong-thing helpful error messages."
Write-Log "stub: publishing host signup"

Write-Say ""
Write-Hr
Write-Host "Step 5 of 6 - Setting up your finance workspace" -ForegroundColor White
Write-Hr
Write-WarnLine "[STUB] Would create %USERPROFILE%\Documents\my-finances\ with subfolder layout,"
Write-WarnLine "       pre-warm the FX cache (24 months), check OneDrive sync and offer to"
Write-WarnLine "       relocate to %USERPROFILE%\finance-workspace\, drop START-HERE on Desktop."
Write-Log "stub: workspace creation"

Write-Say ""
Write-Hr
Write-Host "Step 6 of 6 - Final check" -ForegroundColor White
Write-Hr
Write-WarnLine "[STUB] Would run the diagnostic and report green/red for each component."
Write-Log "stub: diagnostic"

Write-Say ""
Write-Hr
Write-Host "  ✓ Your workspace is ready." -ForegroundColor Green
Write-Hr
Write-Say ""

# B9.2 — seamless first-run handoff. Don't make the user hunt for a Desktop
# icon when momentum is highest. Ask, default-yes, launch straight into the
# workflow if a launcher exists. Desktop shortcut is for re-entry next time.
$WorkspaceRoot   = if ($env:FCB_WORKSPACE) { $env:FCB_WORKSPACE } else { Join-Path $env:USERPROFILE "Documents\my-finances" }
$WorkspaceLauncher = Join-Path $WorkspaceRoot ".skill-launcher.cmd"

if ($Global:AutoMode) {
    Write-Say "Run START-HERE on your Desktop whenever you want to use it."
    Write-Log "completed; auto-mode skipped start-now prompt"
    exit 0
}

$startAnswer = (Read-Host "Want to start now? [Y/n]").Trim().ToLowerInvariant()
if ($startAnswer -in @("", "y", "yes")) {
    if (Test-Path $WorkspaceLauncher) {
        Write-Log "completed; launching workspace"
        Start-Process -FilePath $WorkspaceLauncher -Wait
    } else {
        # Defensive fallback - the workspace-provisioning step always creates
        # this. Only fires if the install was interrupted or someone deleted
        # the launcher between then and now.
        Write-WarnLine "Workspace launcher missing at $WorkspaceLauncher - re-run me to fix."
        Write-Say "Once it's back, double-click START-HERE on your Desktop."
    }
} else {
    Write-Say ""
    Write-Say "Double-click START-HERE on your Desktop whenever you want to use it."
}
Write-Say "You can close this window now."
Write-Log "install completed"
Write-Say ""
Read-Host "Press Enter to close" | Out-Null
