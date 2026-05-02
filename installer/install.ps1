# install.ps1 — Passport to Wealth Finance Clarity bootstrap installer (Windows).
#
# Canonical install path. Designed to be streamed and executed in one shot:
#
#   irm https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.ps1 | iex
#
# (or, via the branded short URL:)
#
#   irm https://passporttowealth.app/install.ps1 | iex
#
# Provisions Node.js, uv (Python toolchain), Python 3.11 via uv, jq, Claude
# Code, the here-now publishing skill, the finance-clarity-build skill (via
# npx skills add), and the workspace at $env:USERPROFILE\Documents\my-finances.
# Leaves no artifacts on the Desktop. Re-entry is `claude` from any PowerShell
# session — the skill knows where the workspace is.
#
# All system-level tools come through winget (Microsoft's official package
# manager, ships with Windows 10 1809+). Non-tools (skills, workspace, deps)
# come through the same channels as the macOS installer (npx skills add, uv).
#
# Mirrors the UX patterns from installer/install.sh: Anthropic data-terms
# consent gate (OP-13), section-by-section pacing, visible printf-style
# prompts (PowerShell's Read-Host can be invisible-prompt-prone too), Ctrl+C
# trap, install log to %LOCALAPPDATA%\PassportToWealth\Logs\.
#
# Full design: dev/finance-clarity-build-spec.md §4. macOS reference:
# installer/install.sh. v0 implementation tracked as backlog #B9.16.
#
# Copyright (c) 2026 Passport to Wealth. All rights reserved.

#Requires -Version 5.1

# Don't use $ErrorActionPreference = 'Stop' globally — many of our brace-style
# fallback patterns rely on Invoke-WebRequest etc. returning non-zero without
# halting the whole script. We handle errors explicitly per call.
$ErrorActionPreference = 'Continue'

# ── ANSI color helpers (PowerShell 7+ supports VT escapes natively;
#    Win10 1809+ Console Host supports them too). For older hosts, we
#    fall back to Write-Host -ForegroundColor. ────────────────────────────────
$Esc = [char]27
$BOLD  = "$Esc[1m"
$DIM   = "$Esc[2m"
$RESET = "$Esc[0m"

function Write-Hr   { Write-Host ("-" * 60) -ForegroundColor DarkGray }
function Write-Say  { param([string]$msg) Write-Host $msg }
function Write-Ok   { param([string]$msg) Write-Host "  $([char]0x2713) $msg" -ForegroundColor Green }
function Write-WarnLine { param([string]$msg) Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-FailLine { param([string]$msg) Write-Host "  X $msg" -ForegroundColor Red }

# ── Args parsing + interactive-state capture ─────────────────────────────────
$Global:AutoMode = $false
$Global:PaceMs = 400
foreach ($a in $args) {
    if ($a -eq "--auto" -or $a -eq "-Auto") {
        $Global:AutoMode = $true
        $Global:PaceMs = 0
    }
}

# When piped from `irm | iex`, PowerShell may treat input as redirected.
# Detect this so prompts know whether to render. INTERACTIVE_DIAG is logged
# below once $LogPath is established — same pattern as install.sh's TTY
# diagnostic. PowerShell exposes this via [Console]::IsInputRedirected.
$Global:Interactive = $true
try {
    if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
        # Try to detach to the host UI — works for `iex (irm ...)` if the
        # console's $Host has a UI we can read from.
        if ($Host.UI -and $Host.UI.RawUI) {
            $Global:InteractiveDiag = "host_ui_ok"
        } else {
            $Global:Interactive = $false
            $Global:AutoMode = $true
            $Global:PaceMs = 0
            $Global:InteractiveDiag = "no_host_ui"
        }
    } else {
        $Global:InteractiveDiag = "stdin_not_redirected"
    }
} catch {
    $Global:Interactive = $false
    $Global:AutoMode = $true
    $Global:PaceMs = 0
    $Global:InteractiveDiag = "detect_failed: $_"
}

function Write-OkPaced  { param([string]$msg) Write-Ok  $msg; if (-not $Global:AutoMode) { Start-Sleep -Milliseconds $Global:PaceMs } }
function Write-SayPaced { param([string]$msg) Write-Say $msg; if (-not $Global:AutoMode) { Start-Sleep -Milliseconds $Global:PaceMs } }

# Pause-ForUser — visible-prompt pattern matching install.sh.
# Print the prompt as a standalone bold line, then read with no -Prompt
# arg (Read-Host -Prompt has the same render-quirk as bash's read -p).
function Pause-ForUser {
    if ($Global:AutoMode -or -not $Global:Interactive) { return }
    Write-Host ""
    Write-Host "$BOLD$([char]9654) Press Enter to continue$RESET"
    [void](Read-Host)
}

# Read-VisiblePrompt — drop-in replacement for Read-Host -Prompt that
# guarantees the prompt text actually appears.
function Read-VisiblePrompt {
    param(
        [string]$Prompt,
        [switch]$AsSecureString
    )
    Write-Host "$BOLD$([char]9654) $Prompt$RESET" -NoNewline
    Write-Host " " -NoNewline
    if ($AsSecureString) {
        return Read-Host -AsSecureString
    } else {
        return Read-Host
    }
}

# ── Log file ────────────────────────────────────────────────────────────────
$LogDir  = Join-Path $env:LOCALAPPDATA "PassportToWealth\Logs"
$LogPath = Join-Path $LogDir "passport-to-wealth-install.log"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
function Write-Log {
    param([string]$msg)
    $ts = (Get-Date).ToUniversalTime().ToString("o")
    Add-Content -Path $LogPath -Value "[$ts] $msg" -ErrorAction SilentlyContinue
}
Write-Log "install.ps1 started"
Write-Log "interactive_state: $($Global:InteractiveDiag) interactive=$($Global:Interactive) auto_mode=$($Global:AutoMode)"

# ── Step tracking + Ctrl+C trap ──────────────────────────────────────────────
$Global:CurrentStep = "pre-consent"
# PowerShell handles Ctrl+C as terminating — we register a handler on the
# TreatControlCAsInput stream so we can log + exit cleanly.
try {
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        if ($LASTEXITCODE -ne 0) {
            Write-Log "user_interrupt at step=$($Global:CurrentStep)"
        }
    } | Out-Null
} catch { }

# Wrapper so any unexpected exit logs the step we were in
trap {
    Write-Log "uncaught_exception at step=$($Global:CurrentStep): $_"
    Write-FailLine "Something went wrong: $_"
    Write-FailLine "See $LogPath for details. Send the log to your advisor."
    exit 1
}

# ── Section 1: welcome + 3-step preview ──────────────────────────────────────
Clear-Host
Write-Hr
Write-Host "Welcome - let's set up your private finance workspace." -ForegroundColor White
Write-Hr
Write-Say ""
Write-Say "I'll do all the technical bits. You'll only need to:"
Write-Say ""
Write-SayPaced "  1. Allow Windows to install some tools (it may ask once)."
Write-SayPaced "  2. Sign in to your AI assistant."
Write-SayPaced "  3. Sign up for the service that hosts your private dashboard (only if you want to share)."
Write-Say ""
Pause-ForUser

# ── Section 2: prototype notice ──────────────────────────────────────────────
Write-Say ""
Write-Hr
Write-Host "  $([char]9888)  PROTOTYPE - pre-release software" -ForegroundColor Yellow
Write-Hr
Write-Say ""
Write-Say "This is a pilot tool for clients of Passport to Wealth, under"
Write-Say "active development. Use it as a complement to - not a replacement"
Write-Say "for - your existing financial records."
Write-Say ""
Write-SayPaced "  - Expect bugs and incomplete features."
Write-SayPaced "  - Always keep your original bank exports and statements."
Write-SayPaced "  - Do not delete source files based on what the dashboard shows."
Write-SayPaced "  - If anything looks wrong, tell your advisor - don't assume the"
Write-Say      "    dashboard is correct."
Write-Say ""
Pause-ForUser

# ── Section 3: Anthropic data-terms consent gate (OP-13) ─────────────────────
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
Write-SayPaced "  - Privacy hub:           https://privacy.anthropic.com/"
Write-SayPaced "  - Privacy policy:        https://www.anthropic.com/legal/privacy"
Write-SayPaced "  - Consumer (Pro/Max):    https://www.anthropic.com/legal/consumer-terms"
Write-SayPaced "  - Commercial (API key):  https://www.anthropic.com/legal/commercial-terms"
Write-SayPaced "  - Trust & security:      https://trust.anthropic.com/"
Write-Say ""
Write-Say "Things to know - and to manage in your Anthropic account settings:"
Write-SayPaced "  - You can opt out of having your conversations used to improve Claude."
Write-SayPaced "  - You can delete your conversation history at any time."
Write-SayPaced "  - Sensitive files (paystubs, tax documents) are skipped by default by"
Write-Say      "    this skill, so their contents are not sent to Claude unless you"
Write-Say      "    explicitly ask."
Write-Say ""
Write-Host "$DIM   One more note: this installer sends an anonymous 'install started' event$RESET"
Write-Host "$DIM   to Passport to Wealth so we know how many clients are onboarding. No IP,$RESET"
Write-Host "$DIM   no name, no machine ID - just 'a Windows install happened today.' Opt out$RESET"
Write-Host "$DIM   by setting `$env:FCB_NO_ANALYTICS=`"1`" before running.$RESET"
Write-Say ""
Write-Say "If you do not accept Anthropic's terms, please stop here and contact"
Write-Say "your advisor - we can talk about alternatives."
Write-Say ""
Pause-ForUser

# Empty input no longer treated as cancel (mirrors install.sh B9.12 fix).
# Only explicit decline words exit. After 5 empties, bail with support pointer.
Write-Say "By typing 'I accept' below you confirm:"
Write-SayPaced "  1. You accept Anthropic's data-handling terms (linked above)."
Write-SayPaced "  2. You understand this is prototype software and you will keep"
Write-Say      "     your original financial records as the source of truth."
Write-Say ""

$consentDone = $false
$emptyCount = 0
while (-not $consentDone) {
    $consent = (Read-VisiblePrompt 'Type "I accept" to continue, or "no" to cancel:').ToString().Trim().ToLowerInvariant()
    switch ($consent) {
        { $_ -in @("i accept","i agree","accept","agree","yes") } {
            Write-Ok "Acceptance recorded."
            Write-Log ("consent_accepted_at=" + (Get-Date).ToUniversalTime().ToString("o") + " (anthropic_data_terms + prototype_status)")
            $consentDone = $true
        }
        { $_ -in @("no","cancel","quit","stop") } {
            Write-Say ""
            Write-Host "No problem - install cancelled. Talk to your advisor any time." -ForegroundColor DarkGray
            Write-Log "consent_declined"
            exit 0
        }
        "" {
            Write-WarnLine "I didn't catch any input. Type 'I accept' to continue, or 'no' to cancel."
            Write-Log "consent_empty_input — possibly interactive_state=$($Global:InteractiveDiag)"
            $emptyCount++
            if ($emptyCount -ge 5) {
                Write-FailLine "I'm not getting any input from you (5 empty replies in a row)."
                Write-FailLine "This usually means PowerShell can't read from your terminal. See:"
                Write-FailLine "  $LogPath"
                Write-FailLine "Send the log to your advisor."
                Write-Log "consent_aborted_after_${emptyCount}_empties interactive_state=$($Global:InteractiveDiag)"
                exit 1
            }
        }
        default {
            Write-WarnLine "I didn't understand. Please type 'I accept' or 'no'."
        }
    }
}

Write-Say ""
Write-Host "$BOLD$([char]9654) Press Enter to begin the install (or Ctrl+C to cancel)$RESET"
[void](Read-Host)

# ── Anonymous install-start ping (Layer 2 telemetry) ─────────────────────────
# Tells Passport to Wealth a non-personal "an install started today on win"
# event so we know how many clients are onboarding. NO IP, NO name, NO machine
# ID — just platform + the build_stamp + advisor_id. Opt out by setting
# $env:FCB_NO_ANALYTICS="1" before running. Disclosed in the consent gate above.
if ($env:FCB_NO_ANALYTICS -ne "1") {
    $pingBuild = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
    $pingBody = @{
        v = 1
        event = "install_started"
        platform = "win"
        build_stamp = $pingBuild
        advisor_id = "passporttowealth"
    } | ConvertTo-Json -Compress
    try {
        # Background job so we don't block install on telemetry network calls
        Start-Job -ScriptBlock {
            param($body)
            try {
                Invoke-RestMethod -Uri "https://passport-feedback.rafaeldf2.workers.dev/install" `
                    -Method POST `
                    -Headers @{
                        "Authorization" = "Bearer n7fQfh_1IYS7pDqsD8O2x0EqMU6l9Mmqu0ZCJWGuqx8"
                        "Content-Type" = "application/json"
                    } `
                    -Body $body `
                    -TimeoutSec 5 `
                    -ErrorAction SilentlyContinue | Out-Null
            } catch { }
        } -ArgumentList $pingBody | Out-Null
        Write-Log "install_started telemetry posted (build=$pingBuild)"
    } catch {
        Write-Log "install_started telemetry post failed: $_"
    }
} else {
    Write-Log "install_started telemetry skipped — FCB_NO_ANALYTICS=1"
}

# ── Step 1/5: Pre-flight (OP-11) ─────────────────────────────────────────────
Write-Say ""
Write-Hr
$Global:CurrentStep = "1/5 pre-flight"
Write-Host "Step 1 of 5 - Checking your computer" -ForegroundColor White
Write-Hr
Write-Log "preflight start"

# Windows version (Win 10 build 1903 / Win 11)
$os = Get-CimInstance Win32_OperatingSystem
$buildNum = [int]$os.BuildNumber
if ($buildNum -lt 18362) {
    Write-FailLine "Your Windows is too old (build $buildNum). I need Windows 10 build 18362 (1903) or later."
    Write-FailLine "FCB-0001"
    Write-Log "FCB-0001 windows_build=$buildNum"
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
    exit 1
}
Write-OkPaced "Personal computer (not MDM-managed)"

# Network reachability
try {
    $resp = Invoke-WebRequest -Uri "https://api.frankfurter.app/latest" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-OkPaced "Network reachable"
} catch {
    Write-WarnLine "Couldn't reach the exchange-rate service. The installer will continue but FX may be stale."
    Write-Log "FCB-0010 network_check_failed: $_"
}

Pause-ForUser

# ── Step 2/5: Tool provisioning via winget ───────────────────────────────────
Write-Say ""
Write-Hr
$Global:CurrentStep = "2/5 installing tools"
Write-Host "Step 2 of 5 - Installing the tools your dashboard needs" -ForegroundColor White
Write-Hr
Write-Say ""

# 2a. winget itself — required for everything else.
# Win10 1809+ ships with App Installer (which provides winget). We check it
# exists; if not, point user at the Microsoft Store install path.
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-FailLine "Windows 'winget' package manager isn't available."
    Write-FailLine "Open the Microsoft Store, search for 'App Installer' from Microsoft, and install it."
    Write-FailLine "Then re-run this command."
    Write-Log "FCB-0020 winget_not_found"
    exit 1
}
Write-OkPaced "winget available"

# 2b. Node.js (provides npx, needed for skill installs in 2g/2h)
if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-OkPaced "Node.js already installed"
} else {
    Write-Say "Installing Node.js (~30s, gives us npx for the next steps)..."
    Write-Log "installing nodejs via winget"
    $wingetArgs = @("install", "OpenJS.NodeJS.LTS", "--silent", "--accept-source-agreements", "--accept-package-agreements")
    $proc = Start-Process winget -ArgumentList $wingetArgs -NoNewWindow -PassThru -Wait -RedirectStandardOutput "$env:TEMP\winget-node.log"
    if ($proc.ExitCode -ne 0) {
        Write-FailLine "Node.js install failed (winget exit $($proc.ExitCode)). See $env:TEMP\winget-node.log"
        Write-Log "FCB-0021 nodejs_install_failed exit=$($proc.ExitCode)"
        exit 1
    }
    # Refresh PATH so we can find node + npx in this session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-OkPaced "Node.js installed"
}

# 2c. uv (Python toolchain)
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-OkPaced "uv already installed"
} else {
    Write-Say "Installing uv (Python toolchain)..."
    Write-Log "installing uv via winget"
    $wingetArgs = @("install", "astral-sh.uv", "--silent", "--accept-source-agreements", "--accept-package-agreements")
    $proc = Start-Process winget -ArgumentList $wingetArgs -NoNewWindow -PassThru -Wait -RedirectStandardOutput "$env:TEMP\winget-uv.log"
    if ($proc.ExitCode -ne 0) {
        Write-FailLine "uv install failed (winget exit $($proc.ExitCode)). See $env:TEMP\winget-uv.log"
        Write-Log "FCB-0022 uv_install_failed exit=$($proc.ExitCode)"
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-OkPaced "uv installed"
}

# 2d. Python 3.11 via uv
Write-Say "Provisioning Python 3.11..."
$pythonInstall = uv python install 3.11 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-FailLine "uv python install 3.11 failed: $pythonInstall"
    Write-Log "FCB-0023 uv_python_install_failed: $pythonInstall"
    exit 1
}
$Global:Python311 = (uv python find 3.11 2>$null | Select-Object -First 1)
if (-not $Global:Python311 -or -not (Test-Path $Global:Python311)) {
    Write-FailLine "uv installed Python 3.11 but couldn't resolve its path."
    Write-Log "FCB-0024 python311_not_found"
    exit 1
}
Write-OkPaced "Python 3.11 ready ($Global:Python311)"

# 2e. jq via winget
if (Get-Command jq -ErrorAction SilentlyContinue) {
    Write-OkPaced "jq already installed"
} else {
    Write-Say "Installing jq..."
    Write-Log "installing jq via winget"
    $wingetArgs = @("install", "jqlang.jq", "--silent", "--accept-source-agreements", "--accept-package-agreements")
    $proc = Start-Process winget -ArgumentList $wingetArgs -NoNewWindow -PassThru -Wait -RedirectStandardOutput "$env:TEMP\winget-jq.log"
    if ($proc.ExitCode -ne 0) {
        Write-FailLine "jq install failed (winget exit $($proc.ExitCode)). See $env:TEMP\winget-jq.log"
        Write-Log "FCB-0025 jq_install_failed exit=$($proc.ExitCode)"
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-OkPaced "jq installed"
}

# 2f. Workspace venv + Python deps
$Global:Workspace = if ($env:FCB_WORKSPACE) { $env:FCB_WORKSPACE } else { Join-Path $env:USERPROFILE "Documents\my-finances" }
New-Item -ItemType Directory -Path $Global:Workspace -Force | Out-Null
$venvPython = Join-Path $Global:Workspace ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-OkPaced "Workspace Python environment already set up"
} else {
    Write-Say "Creating workspace Python environment..."
    $venvPath = Join-Path $Global:Workspace ".venv"
    $venvOut = uv venv --python $Global:Python311 $venvPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-FailLine "uv venv failed: $venvOut"
        Write-Log "FCB-0026 uv_venv_failed: $venvOut"
        exit 1
    }
    Write-OkPaced "Workspace Python environment ready"
}

Write-Say "Installing Python dependencies..."
$pipOut = uv pip install --python $venvPython --quiet "openpyxl~=3.1" "pdfplumber~=0.11" "PyYAML~=6.0" "chardet~=5.2" "reportlab~=4.4" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-FailLine "Python deps install failed: $pipOut"
    Write-Log "FCB-0027 pip_install_failed: $pipOut"
    exit 1
}
Write-OkPaced "Python dependencies installed"

# 2g. Claude Code CLI (via npm — Anthropic's official npm package)
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-OkPaced "Claude Code already installed"
} else {
    Write-Say "Installing Claude Code..."
    Write-Log "installing claude-code via npm"
    $npmOut = npm install -g "@anthropic-ai/claude-code" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-FailLine "Claude Code install failed: $npmOut"
        Write-Log "FCB-0028 claude_install_failed: $npmOut"
        exit 1
    }
    Write-OkPaced "Claude Code installed"
}

# 2h. here-now skill (publishing flow)
$skillsDir = Join-Path $env:USERPROFILE ".claude\skills"
New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
if (Test-Path (Join-Path $skillsDir "here-now")) {
    Write-OkPaced "Publishing-host skill already installed"
} elseif (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    Write-FailLine "npx not available even after Step 2b - see $LogPath and contact your advisor"
    exit 1
} else {
    Write-Say "Installing publishing-host skill..."
    $npxOut = npx -y skills add heredotnow/skill --skill here-now --agent claude-code -g -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-FailLine "here-now skill install failed: $npxOut"
        Write-Log "FCB-0029 here_now_install_failed: $npxOut"
        exit 1
    }
    Write-OkPaced "Publishing-host skill installed"
}

# 2i. finance-clarity-build skill
$Global:SkillRepoRef = if ($env:FCB_SKILL_REPO_REF) { $env:FCB_SKILL_REPO_REF } else { "passporttowealth/passporttowealth" }
$Global:SkillInstallDir = Join-Path $skillsDir "finance-clarity-build"
if (Test-Path (Join-Path $Global:SkillInstallDir "SKILL.md")) {
    Write-Say "Updating finance-clarity-build skill..."
    $npxOut = npx -y skills add $Global:SkillRepoRef --skill finance-clarity-build --agent claude-code -g -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-FailLine "Skill update failed: $npxOut"
        Write-Log "FCB-0030 fcb_update_failed: $npxOut"
        exit 1
    }
    Write-OkPaced "Finance Clarity skill up-to-date"
} else {
    Write-Say "Installing Finance Clarity skill..."
    $npxOut = npx -y skills add $Global:SkillRepoRef --skill finance-clarity-build --agent claude-code -g -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-FailLine "Skill install failed: $npxOut"
        Write-Log "FCB-0031 fcb_install_failed: $npxOut"
        exit 1
    }
    Write-OkPaced "Finance Clarity skill installed"
}

# ── Step 3/5: Claude sign-in ─────────────────────────────────────────────────
Write-Say ""
Write-Hr
$Global:CurrentStep = "3/5 Claude sign-in"
Write-Host "Step 3 of 5 - Signing in to your AI assistant" -ForegroundColor White
Write-Hr
Write-Say ""
Write-Say "How do you sign in to Claude?"
Write-Say "  1. Paid subscription - Claude Pro or Max (sign in with your email)"
Write-Say "  2. Anthropic API key - paste the key (starts with sk-ant-)"
Write-Say ""
Write-Host "  (If you don't have either, please call your advisor - this is" -ForegroundColor DarkGray
Write-Host "  the one step I can't do without you.)" -ForegroundColor DarkGray
Write-Say ""
$authChoice = (Read-VisiblePrompt "Type 1 or 2:").ToString().Trim()

switch ($authChoice) {
    "1" {
        # Subscription path: confirm Claude Code is callable. We don't actively
        # probe OAuth — the previous probe burned subscription quota and picked
        # up stale ANTHROPIC_API_KEY env vars (left by prior installs / other
        # tools), surfacing a misleading "non-zero exit" warning when OAuth
        # was actually fine. When the user runs `claude` for the first time
        # post-install, Claude Code's first-run UX walks them through OAuth
        # if needed.
        if (Get-Command claude -ErrorAction SilentlyContinue) {
            Write-OkPaced "Claude Code ready"
            Write-Host "$DIM   Next time you run 'claude', it'll open your browser to sign in if needed.$RESET"
            Write-Log "claude subscription path - deferring OAuth to user's first claude invocation"
        } else {
            Write-FailLine "Claude Code didn't respond - install may have left it in a bad state"
            exit 1
        }
    }
    "2" {
        Write-Say ""
        $sec = Read-VisiblePrompt "Paste your Anthropic API key (won't be shown):" -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        $apiKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
        $apiKey = $apiKey.Trim()
        if ($apiKey -notmatch "^sk-ant-") {
            Write-FailLine "That doesn't look like an Anthropic API key (should start with sk-ant-)."
            Write-FailLine "FCB-0004"
            Write-Log "FCB-0004 api_key_format_invalid"
            exit 1
        }
        Write-Say "Verifying your API key..."
        try {
            $body = @{
                model = "claude-haiku-4-5"
                max_tokens = 1
                messages = @(@{ role = "user"; content = "." })
            } | ConvertTo-Json -Depth 5
            $resp = Invoke-WebRequest -Uri "https://api.anthropic.com/v1/messages" `
                -Method POST `
                -Headers @{
                    "x-api-key" = $apiKey
                    "anthropic-version" = "2023-06-01"
                    "content-type" = "application/json"
                } `
                -Body $body `
                -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
            Write-OkPaced "API key verified"
        } catch {
            $statusCode = $null
            try { $statusCode = $_.Exception.Response.StatusCode.Value__ } catch {}
            if ($statusCode -in @(401, 403)) {
                Write-FailLine "Anthropic rejected that key (HTTP $statusCode) - check your billing dashboard"
                exit 1
            } else {
                Write-WarnLine "Couldn't verify (error: $_) - saving anyway; you can re-test later"
            }
        }
        # Persist key two ways, mirroring install.sh:
        # 1. Workspace .env (so the skill scripts can read it if needed)
        # 2. User-level environment variable so claude finds it from any new
        #    PowerShell session — Windows equivalent of the shell-rc export.
        $envFile = Join-Path $Global:Workspace ".env"
        if (Test-Path $envFile) {
            (Get-Content $envFile | Where-Object { $_ -notmatch '^ANTHROPIC_API_KEY=' }) | Set-Content $envFile
        }
        Add-Content $envFile "ANTHROPIC_API_KEY=$apiKey"
        # User-scope env var
        [System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $apiKey, "User")
        # Apply to current session too
        $env:ANTHROPIC_API_KEY = $apiKey
        Write-Log "api key saved to workspace .env + User env var"
        Write-Host "$DIM   Note: I saved ANTHROPIC_API_KEY as a User environment variable so claude$RESET"
        Write-Host "$DIM   finds it from any new PowerShell window.$RESET"
    }
    default {
        Write-FailLine "I didn't understand. Run me again and pick 1 or 2."
        exit 1
    }
}
Write-OkPaced "AI assistant ready"

# ── Step 4/5: Workspace setup ────────────────────────────────────────────────
Write-Say ""
Write-Hr
$Global:CurrentStep = "4/5 workspace setup"
Write-Host "Step 4 of 5 - Setting up your finance workspace" -ForegroundColor White
Write-Hr
Write-Say ""

# Create canonical subfolders
foreach ($sub in @("inbox","01_bank_transactions","02_payslips","03_amazon_orders","04_reference_docs","05_other","pipeline\output","fx_cache")) {
    New-Item -ItemType Directory -Path (Join-Path $Global:Workspace $sub) -Force | Out-Null
}
Write-OkPaced "Workspace folders created at $Global:Workspace"

# Bootstrap config.yaml from the skill's example
$configFile = Join-Path $Global:Workspace "config.yaml"
$skillConfig = Join-Path $Global:SkillInstallDir "config.example.yaml"
if (-not (Test-Path $configFile) -and (Test-Path $skillConfig)) {
    Copy-Item $skillConfig $configFile
    Write-OkPaced "Workspace config created"
}

# FX cache pre-warm — last 24 months, similar to install.sh Step 5d.
# Failures are non-fatal; the pipeline will fetch on first use.
$fxFetch = Join-Path $Global:SkillInstallDir "scripts\fx_fetch.py"
if (Test-Path $fxFetch) {
    Write-Say "Pre-warming exchange-rate cache (last 24 months)..."
    $endDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
    $startDate = (Get-Date).AddMonths(-24).ToUniversalTime().ToString("yyyy-MM-dd")
    $env:FCB_WORKSPACE = $Global:Workspace
    try {
        & $venvPython $fxFetch --base EUR --pairs USD,GBP --start $startDate --end $endDate 2>&1 | Out-Null
        Write-OkPaced "Exchange rate cache pre-warmed"
    } catch {
        Write-WarnLine "FX pre-warm failed - pipeline will fetch on first use instead"
        Write-Log "fx_prewarm_failed: $_"
    }
}

# OneDrive sync detection deferred to v1.1 (B9.16 follow-up).

Pause-ForUser

# ── Step 5/5: Diagnostics ────────────────────────────────────────────────────
Write-Say ""
Write-Hr
$Global:CurrentStep = "5/5 final diagnostics"
Write-Host "Step 5 of 5 - Final check" -ForegroundColor White
Write-Hr
Write-Say ""

$DiagnosticFails = 0
function Test-Diagnostic {
    param([string]$Label, [scriptblock]$Test)
    try {
        $result = & $Test
        if ($result) {
            Write-Ok $Label
            return $true
        } else {
            Write-FailLine $Label
            $script:DiagnosticFails++
            return $false
        }
    } catch {
        Write-FailLine "$Label (error: $_)"
        $script:DiagnosticFails++
        return $false
    }
}

[void](Test-Diagnostic "winget available"            { [bool](Get-Command winget -ErrorAction SilentlyContinue) })
[void](Test-Diagnostic "Node.js installed (npx)"     { [bool](Get-Command npx -ErrorAction SilentlyContinue) })
[void](Test-Diagnostic "uv installed"                { [bool](Get-Command uv -ErrorAction SilentlyContinue) })
[void](Test-Diagnostic "Python 3.11 installed"       { Test-Path $Global:Python311 })
[void](Test-Diagnostic "jq installed"                { [bool](Get-Command jq -ErrorAction SilentlyContinue) })
[void](Test-Diagnostic "Claude Code installed"       { [bool](Get-Command claude -ErrorAction SilentlyContinue) })
[void](Test-Diagnostic "Workspace folder"            { Test-Path $Global:Workspace })
[void](Test-Diagnostic "Workspace venv"              { Test-Path $venvPython })
[void](Test-Diagnostic "Workspace config"            { Test-Path $configFile })
[void](Test-Diagnostic "Publishing-host skill"       { Test-Path (Join-Path $skillsDir "here-now") })
[void](Test-Diagnostic "Finance Clarity skill"       { Test-Path (Join-Path $Global:SkillInstallDir "SKILL.md") })
[void](Test-Diagnostic "FX cache directory"          { Test-Path (Join-Path $Global:Workspace "fx_cache") })

if ($DiagnosticFails -gt 0) {
    Write-WarnLine "$DiagnosticFails diagnostic check(s) reported issues - see $LogPath."
    Write-WarnLine "If something misbehaves when you run claude, re-run this installer or"
    Write-WarnLine "share the log with your advisor."
    Write-Log "diagnostic_failures count=$DiagnosticFails"
} else {
    Write-OkPaced "All diagnostics passed"
}

Write-Say ""
Write-Hr
Write-Host "  $([char]10003) Your workspace is ready." -ForegroundColor Green
Write-Hr
Write-Say ""
Write-Log "install completed"

# In-process seamless handoff: ask if the user wants to start now. Default
# Y so a single Enter keeps momentum. On Y we cd into the workspace + invoke
# claude with --add-dir + an initial prompt. Mirrors install.sh.
if ($Global:AutoMode -or -not $Global:Interactive) {
    Write-Host "$BOLD$([char]9654) Anytime you want to use it: open PowerShell and type 'claude'$RESET"
    Write-Host "   Drop financial files in: $Global:Workspace\inbox\"
    Write-Say ""
    exit 0
}

$startAnswer = (Read-VisiblePrompt "Want to start now? [Y/n]").ToString().Trim().ToLowerInvariant()
if ($startAnswer -in @("", "y", "yes")) {
    Write-Log "starting claude with primer prompt"
    $env:FCB_WORKSPACE = $Global:Workspace
    Set-Location $Global:Workspace
    $primer = "Welcome. Drop your financial files into $Global:Workspace\inbox\ and say 'build my report' when you're ready."
    # PowerShell doesn't have an `exec`. Calling claude directly will run it
    # in the foreground; when the user exits claude they're back at the
    # PowerShell prompt that launched the install command.
    & claude --add-dir $Global:Workspace $primer
} else {
    Write-Say ""
    Write-Say "OK. Anytime you want to use it:"
    Write-SayPaced "  1. Open PowerShell (press Win, type PowerShell, hit Enter)"
    Write-SayPaced "  2. Type:  claude"
    Write-SayPaced "  3. Tell it 'build my report' or 'refresh my finances'"
    Write-Say ""
    Write-Say "Drop your bank statements and other files in:"
    Write-Host "  $Global:Workspace\inbox\" -ForegroundColor White
    Write-Say ""
    Write-Host "$DIM   The skill knows where your workspace is - no need to navigate to it.$RESET"
    Write-Say ""
}
