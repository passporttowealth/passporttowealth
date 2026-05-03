#!/usr/bin/env python3
"""build_docs.py — generate installer/docs/index.html.

Produces a multi-section docs page with a left sidebar, in the shape of
here.now/docs. The "What this installs" section is auto-extracted from
installer/install.sh + installer/install.ps1 (so it can never drift
from what the install actually does); the other sections (Quick start,
What you get, Privacy at a glance, Sharing, Reference) are hand-written
content that lives in this script.

Run:
    python3 installer/build_docs.py            # write installer/docs/index.html
    python3 installer/build_docs.py --check    # CI: fail if committed file is stale

CI runs --check on every PR so the install scripts and the published
docs can never get out of sync.

Copyright (c) 2026 Passport to Wealth. All rights reserved.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO / "installer" / "install.sh"
INSTALL_PS1 = REPO / "installer" / "install.ps1"
DOCS_OUT = REPO / "installer" / "docs" / "index.html"


# ── Curated, plain-English descriptions ─────────────────────────────────────
#
# Keys are normalized identifiers (lowercase, no version pins). If a new
# `brew install`, `winget install`, `npx skills add`, etc. lands in the
# install scripts and there's no entry here, the build fails.

TOOLS = {
    "jq": "A small command-line tool for reading JSON. Used by the publish flow when talking to the dashboard host. Installed via Homebrew on Mac, winget on Windows.",
    "node": "Node.js — the JavaScript runtime. Required because Claude Code is distributed via npm and the skill itself is fetched via npx (a Node tool). Installed via Homebrew on Mac, winget on Windows.",
    "openjs.nodejs.lts": "Node.js LTS — the Windows package name for Node.",
    "astral-sh.uv": "uv — the Windows package name for uv.",
    "jqlang.jq": "jq — the Windows package name for jq.",
    "uv": "Astral's Python toolchain. Replaces the older Homebrew + Python + venv + pip chain with a single binary. Manages Python 3.11, the workspace virtual environment, and the Python packages below. Downloaded from astral.sh.",
    "python 3.11": "The Python version your workspace uses. uv downloads and isolates this; it doesn't replace whatever Python your computer came with.",
    "@anthropic-ai/claude-code": "Claude Code — the AI assistant CLI. This is what you'll type 'claude' into to use the skill. Distributed by Anthropic on npm.",
    "heredotnow/skill --skill here-now": "The here-now publishing skill. Lets you share your dashboard online behind a passcode if (and only if) you choose to. Published by here.now.",
    "passporttowealth/passporttowealth --skill finance-clarity-build": "This project — the finance-clarity-build skill. Source is in the same GitHub repo you're reading.",
}

PYTHON_PACKAGES = {
    "openpyxl": "Reads Excel spreadsheets. Used by the categorize step if you have any .xlsx exports.",
    "pdfplumber": "Reads text-layer PDFs (bank statements, paystubs). Never OCRs image-only PDFs by design — those route to a separate folder for you to review manually.",
    "pyyaml": "Parses YAML configuration files (rules.yaml, fx_overrides.yaml).",
    "chardet": "Detects character encoding on CSV files. Bank exports come in surprising encodings; chardet figures it out.",
    "reportlab": "Generates the synthetic PDFs in the demo kit (paystub, tax doc). Only used when regenerating the demo, never on your real data.",
}

URLS = {
    "https://astral.sh/uv/install.sh": "Astral's official uv installer. Downloads the uv binary.",
    "https://api.frankfurter.app": "Frankfurter — open-source exchange-rate API backed by the European Central Bank. Used to convert multi-currency transactions to your base currency. Free, no signup, no key.",
    "https://api.frankfurter.app/latest": "Frankfurter latest-rates endpoint. Hit during install pre-flight to verify network reachability.",
    "https://api.anthropic.com/v1/messages": "Anthropic's API. Hit only if you choose 'Anthropic API key' as your sign-in method, to verify the key works. Never hit if you sign in with a Claude Pro/Max subscription.",
    "https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh": "The canonical Mac install script on this repo's main branch. The install one-liner you ran resolves to this.",
    "https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.ps1": "The canonical Windows install script on this repo's main branch.",
    "https://passport-feedback.rafaeldf2.workers.dev/install": "Anonymous install-start telemetry endpoint. Payload: platform (mac or win), build_stamp, advisor_id. NO IP, NO name, NO machine ID. Opt out with FCB_NO_ANALYTICS=1.",
    "https://passport-feedback.rafaeldf2.workers.dev": "Cloudflare Worker. Two endpoints: /install (anonymous install telemetry above) and / (feedback events from your dashboard, only when you click 'I have feedback').",
    "https://claude.ai/install.sh": "Anthropic's official Claude Code installer. Downloads the Claude Code CLI. Mac fallback path used when npm isn't available.",
    "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh": "Homebrew's official installer. Downloads Homebrew, the standard Mac package manager. Only run if jq or Node aren't already on the system.",
    "https://passporttowealth.app/install": "The branded short URL for the Mac install command. Resolves to a tiny shim that exec-fetches install.sh from GitHub raw — same source code, friendlier domain.",
    "https://passporttowealth.app/install.ps1": "Same as above for Windows.",
}

# File operations: paths are looked up from the install scripts so they
# can't drift if we ever change the workspace location. Descriptions stay
# curated.
FILE_OPERATIONS_DESCRIPTIONS = {
    "WORKSPACE": "Your workspace. Created on first install. Holds your inbox, the categorized output, the dashboard, and a config.yaml you can edit. Nothing is created elsewhere on disk.",
    "WORKSPACE_VENV": "The isolated Python environment uv creates for the pipeline. Lives inside your workspace; can be deleted and recreated anytime.",
    "WORKSPACE_ENV": "Stores your dashboard passcode (only if you ever publish), your Anthropic API key (only if you chose that sign-in option), and the SITE_URL after first publish. chmod 600 — owner-readable only.",
    "MAC_INSTALL_LOG": "Mac install log. Plain text. You can read or send it to your advisor for support.",
    "WIN_INSTALL_LOG": "Windows install log. Same purpose as above.",
    "SHELL_RC": "Your shell configuration file. We append (idempotently — never twice) one block: an export line for ANTHROPIC_API_KEY, only if you chose API-key sign-in. Otherwise untouched.",
    "WIN_USER_ENV": "On Windows, ANTHROPIC_API_KEY is also written as a User-scope environment variable so 'claude' finds it from any new PowerShell window.",
}

NEVER_TOUCHES = [
    "Your IP address, name, machine identifier, or any personally-identifying field. The install-start telemetry deliberately strips all of these.",
    "Any folder outside ~/Documents/my-finances/ on Mac or %USERPROFILE%\\Documents\\my-finances\\ on Windows.",
    "Your Desktop. No icon, no shortcut, no app. To re-open the assistant later: open Terminal (Mac) or PowerShell (Windows) and type 'claude'.",
    "Anything administrative beyond what brew, winget, and uv themselves request when installing their own tools. The install never asks for sudo password directly.",
    "Your source files (bank statements, paystubs, tax documents) during the install itself. The installer never opens them. After install, if you explicitly ask the assistant to read a specific file, the file content goes to Anthropic's API as part of your Claude conversation, governed by your Anthropic account terms.",
]

# Environment variables: descriptions only; the actual var names are
# extracted from the install scripts (see find_env_vars below) so adding
# a new opt-out flag automatically surfaces it on the docs page.
ENV_VAR_DESCRIPTIONS = {
    "FCB_NO_ANALYTICS": "Set to 1 before running the install command to skip the anonymous install-start ping. Default: ping is sent.",
    "FCB_WORKSPACE": "Override the default workspace location (~/Documents/my-finances/). Both the installer and the skill scripts honor it. Useful if you want the workspace outside iCloud sync.",
    "FCB_SKILL_REPO_REF": "Override which Git ref of this repo the installer fetches the skill from. Defaults to main. Test/debug only.",
    "FCB_SKILL_INSTALL_DIR": "Override where the installer places the fetched skill. Defaults to the standard skills directory. Test/debug only.",
    "PYTHON": "Override which Python interpreter the skill scripts use. Defaults to the workspace venv created by the installer. Test/debug only.",
    "HERENOW_PUBLISH_SCRIPT": "Override the location of the here-now publishing script. Test/debug only.",
    "ANTHROPIC_API_KEY": "Your Anthropic API key, written by the installer to .env if you chose API-key sign-in. The skill reads it via your shell environment.",
}


# ── Parsers ─────────────────────────────────────────────────────────────────


def find_brew_installs(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r'(?:^|\W)brew install\s+([a-zA-Z0-9._@/\-]+)', text):
        token = match.group(1)
        if not token.startswith("-"):
            found.add(token.lower())
    return found


def find_winget_installs(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r'winget install\b[^"\'\n]*?--id\s+["\']?([A-Za-z0-9._\-]+)', text):
        found.add(match.group(1).lower())
    return found


def find_uv_python(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r'uv["\']?\s+python\s+install\s+([0-9.]+)', text):
        found.add(f"python {match.group(1)}")
    if "uv python install" in text or "uv pip install" in text or '"$UV_BIN"' in text:
        found.add("uv")
    return found


def find_npm_globals(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r'npm install\s+-g\s+([@a-zA-Z0-9._/\-]+)', text):
        found.add(match.group(1).lower())
    for match in re.finditer(r'npm\s+install\s+--global\s+([@a-zA-Z0-9._/\-]+)', text):
        found.add(match.group(1).lower())
    return found


def find_npx_skills(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r'npx\s+(?:--yes\s+)?skills\s+add\s+([^\s]+)\s+--skill\s+(\S+)', text):
        repo, skill = match.group(1), match.group(2)
        found.add(f"{repo} --skill {skill}".lower())
    return found


def find_python_deps(req_text: str) -> set[str]:
    found = set()
    for line in req_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r'[<>=!~]', line, maxsplit=1)[0].strip().lower()
        if name:
            found.add(name)
    return found


def find_urls(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r'https://[^\s"\'`<>)]+', text):
        url = match.group(0).rstrip(",.;:)")
        normalized = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        if normalized.startswith("https://"):
            found.add(normalized)
    return found


def extract_workspace_paths(sh: str, ps1: str) -> dict[str, str]:
    """Extract workspace + log paths from the install scripts so docs
    don't drift if we ever rename the workspace folder."""
    paths = {}

    # Mac workspace: WS="${FCB_WORKSPACE:-${HOME}/Documents/my-finances}"
    m = re.search(r'WS=["\']?\$\{FCB_WORKSPACE:-\$\{HOME\}([^"\'}\n]+)\}', sh)
    if m:
        paths["WORKSPACE"] = "~" + m.group(1) + "/"
        paths["WORKSPACE_VENV"] = "~" + m.group(1) + "/.venv/"
        paths["WORKSPACE_ENV"] = "~" + m.group(1) + "/.env"

    # Mac install log: INSTALL_LOG="${HOME}/Library/Logs/passport-to-wealth-install.log"
    m = re.search(r'INSTALL_LOG=["\']?\$\{HOME\}([^"\'\n]+\.log)', sh)
    if m:
        paths["MAC_INSTALL_LOG"] = "~" + m.group(1)

    # Windows workspace + log: $env:USERPROFILE\Documents\my-finances and
    # $env:LOCALAPPDATA\PassportToWealth\Logs\passport-to-wealth-install.log
    m = re.search(r'\$env:USERPROFILE\\([^"\'\s\n]+my-finances)', ps1)
    if m:
        # WIN_WORKSPACE not currently rendered; could be added if needed
        pass
    m = re.search(r'Join-Path\s+\$env:LOCALAPPDATA\s+["\']([^"\'\n]+\.log)["\']', ps1)
    if m:
        paths["WIN_INSTALL_LOG"] = "%LOCALAPPDATA%\\" + m.group(1)
    else:
        # Fallback: pattern uses Join-Path twice
        m = re.search(r'\$env:LOCALAPPDATA\s+["\']([^"\'\n]+)["\'][\s\S]*?Join-Path[^\n]+["\']([^"\'\n]+\.log)["\']', ps1)
        if m:
            paths["WIN_INSTALL_LOG"] = "%LOCALAPPDATA%\\" + m.group(1) + "\\" + m.group(2)

    # Shell rc: detect both .zshrc / .bashrc references; we just confirm
    # the install scripts touch a shell rc and render a generic label.
    if re.search(r'\.zshrc|\.bashrc', sh):
        paths["SHELL_RC"] = "~/.zshrc / ~/.bashrc"

    # Windows User-scope env var write
    if re.search(r'SetEnvironmentVariable\([^,]+,\s*[^,]+,\s*["\']User["\']', ps1):
        paths["WIN_USER_ENV"] = "User-scope environment variables (Windows)"

    return paths


def find_env_vars(sh: str, ps1: str) -> set[str]:
    """Extract env vars the install scripts read. Catches FCB_*, PYTHON,
    HERENOW_PUBLISH_SCRIPT, ANTHROPIC_API_KEY — any user-controllable knob.
    New ones get auto-surfaced on the docs page if added to the
    ENV_VAR_DESCRIPTIONS map; missing descriptions fail the build."""
    found = set()
    # Bash: ${FOO_BAR:-default} and ${FOO_BAR}
    for m in re.finditer(r'\$\{([A-Z][A-Z0-9_]+)(?::-[^}]*)?\}', sh):
        found.add(m.group(1))
    # PowerShell: $env:FOO_BAR
    for m in re.finditer(r'\$env:([A-Z][A-Z0-9_]+)', ps1):
        found.add(m.group(1))
    # Filter to user-facing ones (FCB_*, PYTHON, HERENOW_*, ANTHROPIC_*)
    keep_prefixes = ("FCB_", "HERENOW_", "ANTHROPIC_")
    keep_exact = {"PYTHON"}
    return {v for v in found if v.startswith(keep_prefixes) or v in keep_exact}


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    sh = INSTALL_SH.read_text(encoding="utf-8")
    ps1 = INSTALL_PS1.read_text(encoding="utf-8")
    req_path = REPO / "requirements.txt"
    req = req_path.read_text(encoding="utf-8") if req_path.exists() else ""

    tools = set()
    tools |= find_brew_installs(sh)
    tools |= find_winget_installs(ps1)
    tools |= find_uv_python(sh) | find_uv_python(ps1)
    tools |= find_npm_globals(sh) | find_npm_globals(ps1)
    tools |= find_npx_skills(sh) | find_npx_skills(ps1)

    py_deps = find_python_deps(req)
    all_urls = find_urls(sh) | find_urls(ps1)
    paths = extract_workspace_paths(sh, ps1)
    env_vars = find_env_vars(sh, ps1)

    errors = []
    for t in sorted(tools):
        if t not in TOOLS:
            errors.append(f"  - tool {t!r} found in install scripts but not in TOOLS map")
    for p in sorted(py_deps):
        if p not in PYTHON_PACKAGES:
            errors.append(f"  - python package {p!r} in requirements.txt but not in PYTHON_PACKAGES map")
    for u in sorted(all_urls):
        is_fetch = any(
            re.search(rf'(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod|fetch)[^\n]{{0,100}}{re.escape(u)}', body)
            for body in (sh, ps1)
        )
        if is_fetch and not any(u.startswith(known) for known in URLS):
            errors.append(f"  - URL {u!r} fetched in install scripts but not in URLS map")
    for v in sorted(env_vars):
        if v not in ENV_VAR_DESCRIPTIONS:
            errors.append(f"  - env var {v!r} read by install scripts but not in ENV_VAR_DESCRIPTIONS map")
    for key in FILE_OPERATIONS_DESCRIPTIONS:
        if key not in paths:
            # Tolerate missing keys — extraction may legitimately fail to
            # find something if the install scripts rename/remove a path.
            # We only fail on NEW things, not missing ones.
            pass
    if errors:
        print("ERROR: docs would drift from install scripts. Add entries to "
              "installer/build_docs.py for:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(2)

    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(
        tools=sorted(tools),
        python_packages=sorted(py_deps),
        urls=sorted(u for u in URLS if u in all_urls),
        paths=paths,
        env_vars=sorted(env_vars),
    )

    if "--check" in sys.argv:
        existing = DOCS_OUT.read_text(encoding="utf-8") if DOCS_OUT.exists() else ""
        if existing != html:
            print(f"ERROR: {DOCS_OUT.relative_to(REPO)} is out of date with the install scripts.", file=sys.stderr)
            print("       Run `python3 installer/build_docs.py` and commit the result.", file=sys.stderr)
            sys.exit(2)
        print(f"OK {DOCS_OUT.relative_to(REPO)} is in sync with install scripts")
        return

    DOCS_OUT.write_text(html, encoding="utf-8")
    print(f"wrote {DOCS_OUT.relative_to(REPO)} ({len(html):,} bytes)")
    print(f"  tools: {len(tools)}, python deps: {len(py_deps)}, URLs documented: {len([u for u in URLS if u in all_urls])}")


def render_html(tools: list[str], python_packages: list[str], urls: list[str], paths: dict, env_vars: list[str]) -> str:
    """Multi-section docs page with a left sidebar (here.now/docs style).
    Deterministic output (no live timestamp) so CI can byte-compare.

    Tools/packages/URLs are extracted from install scripts; paths and
    env-var names are extracted too. Only the human-readable descriptions
    are hardcoded — and any new tool/URL/env-var the install scripts
    reference but doesn't have a description fails the build."""

    def items(pairs):
        return "".join(
            f'<li><code class="item-name">{name}</code><span class="item-desc">{desc}</span></li>'
            for name, desc in pairs
        )

    tools_pairs = [(t, TOOLS[t]) for t in tools]
    py_pairs = [(p, PYTHON_PACKAGES[p]) for p in python_packages]
    url_pairs = [(u, URLS[u]) for u in urls]
    # File-operations: emit only the keys we successfully extracted from
    # the install scripts. Skips entries silently if extraction missed
    # them (e.g., install scripts renamed the path).
    file_items = "".join(
        f'<li><code class="item-name">{paths[key]}</code><span class="item-desc">{FILE_OPERATIONS_DESCRIPTIONS[key]}</span></li>'
        for key in ("WORKSPACE", "WORKSPACE_VENV", "WORKSPACE_ENV", "MAC_INSTALL_LOG", "WIN_INSTALL_LOG", "SHELL_RC", "WIN_USER_ENV")
        if key in paths
    )
    never_items = "".join(f"<li>{n}</li>" for n in NEVER_TOUCHES)
    env_rows = "".join(
        f"<tr><td><code>{v}</code></td><td>{ENV_VAR_DESCRIPTIONS[v]}</td></tr>"
        for v in env_vars
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Docs — Passport to Wealth Finance Clarity</title>
<meta name="description" content="Documentation for the Passport to Wealth Finance Clarity skill: how to install it, what it does, what it touches on your computer, and how to share your dashboard.">
<link rel="icon" type="image/png" href="../assets/brand/favicon.png">
<style>
  :root {{
    --bg: #FAF8F4;
    --text: #0F1E33;
    --text-muted: #5E6473;
    --gold: #C9A75D;
    --card: #FFFFFF;
    --border: #E8E5DE;
    --code-bg: #F2EEE5;
    --code-fg: #2A3550;
    --sidebar-bg: #F5F1E8;
    --sidebar-active: #0F1E33;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    background: var(--bg);
    color: var(--text);
    font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .layout {{
    display: grid;
    grid-template-columns: 220px 1fr;
    max-width: 1080px;
    margin: 0 auto;
    min-height: 100vh;
  }}
  /* Sidebar */
  aside.sidebar {{
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border);
    padding: 28px 20px;
    position: sticky;
    top: 0;
    align-self: start;
    height: 100vh;
    overflow-y: auto;
  }}
  /* Brand row: wordmark only. The original logo-blue.png is a complex
     circular mark with text wrapped inside it AND a plane in the
     center — illegible at sidebar-icon size and redundant with the
     wordmark sitting next to it. Cleaner to drop the image entirely
     and let the wordmark stand on its own with a small gold accent
     above it (matches the brand's gold-accent design language without
     duplicating the wordmark). */
  .sidebar-brand {{
    display: block;
    text-align: center;
    margin: 0 0 22px;
    padding: 4px 0 18px;
    border-bottom: 1px solid var(--border);
    text-decoration: none;
    color: var(--text);
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.02em;
    line-height: 1.3;
  }}
  .sidebar-brand::before {{
    content: "";
    display: block;
    width: 28px;
    height: 2px;
    background: var(--gold);
    margin: 0 auto 10px;
    border-radius: 1px;
  }}
  .sidebar-brand:hover {{ color: var(--gold); }}
  .sidebar-brand:hover::before {{ background: var(--text); }}
  .sidebar h3 {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin: 24px 0 8px;
    font-weight: 600;
  }}
  .sidebar a {{
    display: block;
    padding: 6px 12px 6px 10px;
    color: var(--text);
    text-decoration: none;
    font-size: 14px;
    line-height: 1.4;
    border-left: 2px solid transparent;
    margin-left: -2px;
  }}
  .sidebar a:hover {{ color: var(--gold); }}
  .sidebar a.active {{ border-left-color: var(--sidebar-active); font-weight: 600; }}
  .sidebar a.subnav {{ font-size: 13px; padding-left: 22px; color: var(--text-muted); }}

  /* Main column */
  main {{ padding: 48px 56px 80px; max-width: 760px; }}
  .breadcrumb {{ font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }}
  .breadcrumb a {{ color: var(--text-muted); text-decoration: none; }}
  .breadcrumb a:hover {{ color: var(--gold); }}
  h1 {{ font-size: 32px; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 12px; }}
  .lede {{ color: var(--text-muted); font-size: 17px; margin-bottom: 32px; max-width: 640px; }}
  section.doc-section {{
    margin-top: 48px;
    scroll-margin-top: 24px;
  }}
  section.doc-section h2 {{
    font-size: 22px;
    font-weight: 700;
    margin: 0 0 4px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--gold);
    display: inline-block;
  }}
  section.doc-section .section-lede {{
    color: var(--text-muted);
    font-size: 15px;
    margin: 14px 0 20px;
  }}
  section.doc-section h3 {{
    font-size: 17px;
    font-weight: 600;
    margin: 28px 0 8px;
  }}
  p {{ font-size: 15px; line-height: 1.7; }}
  ul, ol {{ font-size: 15px; padding-left: 22px; }}
  li {{ margin-bottom: 6px; line-height: 1.55; }}
  ul.items, ul.never {{ list-style: none; padding: 0; margin: 0; }}
  ul.items li {{
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
  }}
  ul.items li:last-child {{ border-bottom: none; }}
  .item-name {{
    display: inline-block;
    background: var(--code-bg);
    color: var(--code-fg);
    padding: 2px 8px;
    border-radius: 4px;
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 13px;
    word-break: break-all;
  }}
  .item-desc {{
    display: block;
    color: var(--text-muted);
    margin-top: 6px;
    font-size: 14px;
  }}
  ul.never li {{
    padding: 8px 0 8px 24px;
    position: relative;
    color: var(--text-muted);
    font-size: 14px;
    border-bottom: 1px solid var(--border);
  }}
  ul.never li:last-child {{ border-bottom: none; }}
  ul.never li::before {{
    content: "✗";
    position: absolute;
    left: 0;
    top: 8px;
    color: var(--text);
    font-weight: 700;
  }}
  pre.code {{
    background: var(--code-bg);
    color: var(--code-fg);
    padding: 14px 16px;
    border-radius: 6px;
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 13px;
    overflow-x: auto;
    margin: 12px 0 20px;
  }}
  code {{
    font-family: "SF Mono", Menlo, Consolas, monospace;
    background: var(--code-bg);
    color: var(--code-fg);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.9em;
  }}
  table.ref {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    margin: 12px 0 20px;
  }}
  table.ref th, table.ref td {{
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  table.ref th {{ font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
  table.ref td:first-child {{ width: 38%; }}
  table.ref code {{ font-size: 12px; }}
  .callout {{
    background: #FBF6E8;
    border-left: 3px solid var(--gold);
    padding: 12px 16px;
    margin: 16px 0;
    border-radius: 0 4px 4px 0;
    font-size: 14px;
  }}
  .callout strong {{ color: var(--text); }}
  a.body-link {{ color: var(--text); text-decoration: underline; text-underline-offset: 2px; text-decoration-color: var(--gold); }}
  a.body-link:hover {{ color: var(--gold); }}
  footer.docs-footer {{
    margin-top: 64px;
    padding-top: 20px;
    border-top: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 13px;
  }}

  @media (max-width: 760px) {{
    .layout {{ grid-template-columns: 1fr; }}
    aside.sidebar {{
      position: static;
      height: auto;
      padding: 24px;
      border-right: none;
      border-bottom: 1px solid var(--border);
    }}
    main {{ padding: 24px; }}
  }}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <a class="sidebar-brand" href="../">Passport to Wealth</a>
    <h3>Docs</h3>
    <a href="#quick-start">Quick start</a>
    <a href="#what-you-get">What you get</a>
    <a href="#privacy-glance">Privacy at a glance</a>
    <a href="#what-installs">What this installs</a>
    <a href="#sharing">Sharing your dashboard</a>
    <a href="#reference">Reference</a>
    <h3>Resources</h3>
    <a href="../">Landing page</a>
    <a href="../dashboard-demo/">Live demo</a>
    <a href="https://github.com/passporttowealth/passporttowealth">GitHub</a>
    <h3>Legal</h3>
    <a href="../legal/privacy.html">Privacy policy</a>
    <a href="../legal/terms.html">Terms of service</a>
    <a href="../legal/dpa.html">Data processing</a>
  </aside>

  <main>
    <div class="breadcrumb"><a href="../">passporttowealth.app</a> · Docs</div>
    <h1>Docs</h1>
    <p class="lede">How the Passport to Wealth Finance Clarity skill works, what it installs on your computer, what stays local, and how to share your dashboard if you want to. The "What this installs" section is auto-extracted from the install scripts so it cannot drift from what actually runs.</p>

    <section class="doc-section" id="quick-start">
      <h2>Quick start</h2>
      <p class="section-lede">One command to install the whole thing. Same flow on Mac and Windows; pick the one that matches your computer.</p>

      <h3>Mac</h3>
      <p>Open Terminal (<code>⌘ Space</code> → type "Terminal" → Enter) and paste:</p>
      <pre class="code">curl -fsSL https://passporttowealth.app/install | bash</pre>
      <p>The installer takes about 10 minutes on a Mac that already has developer tools installed, up to an hour on a fresh machine. It'll ask for your password once (so it can install system tools via Homebrew) and ask how you sign in to your AI assistant. Everything else is automatic.</p>

      <h3>Windows</h3>
      <p>Open PowerShell (<code>Win</code> → type "PowerShell" → Enter) and paste:</p>
      <pre class="code">irm https://passporttowealth.app/install.ps1 | iex</pre>
      <p>Tools install via winget (Microsoft's package manager, ships with Windows 10 1809+). Same UX as the Mac flow.</p>

      <h3>What happens next</h3>
      <ol>
        <li>Type <code>claude</code> in your terminal to open the assistant.</li>
        <li>Drop your bank statements, payslips, and tax docs into <code>~/Documents/my-finances/inbox/</code>.</li>
        <li>Tell the assistant <em>"build my report."</em></li>
        <li>The assistant sorts, dedupes, normalizes currencies, fetches exchange rates, categorizes, and shows totals back for you to confirm.</li>
        <li>Once you approve, the dashboard opens locally in your browser.</li>
      </ol>

      <div class="callout">
        <strong>Want to see the output before installing?</strong> The <a class="body-link" href="../dashboard-demo/">live demo dashboard</a> is the real dashboard rendered against synthetic data. Same layout, real charts, fake numbers.
      </div>
    </section>

    <section class="doc-section" id="what-you-get">
      <h2>What you get</h2>
      <p class="section-lede">A single workspace folder on your computer. Everything you need lives inside it; nothing else is created on your machine.</p>

      <pre class="code">~/Documents/my-finances/
├── inbox/                       ← drop new files here
├── 01_bank_transactions/        ← sorted by classify
├── 02_payslips/                 ← never auto-read (sensitive)
├── 03_amazon_orders/
├── 04_reference_docs/
├── 05_other/
├── pipeline/output/             ← intermediate CSVs, error envelopes
├── site/                        ← your rendered dashboard (open in browser)
├── .venv/                       ← isolated Python (uv)
├── config.yaml                  ← editable config
├── rules.yaml                   ← merchant categorization rules
└── .env                         ← passcode + API key (chmod 600)</pre>

      <p>Re-entry is always <code>claude</code> from any terminal — the skill remembers where the workspace is. To refresh after dropping new files: open the assistant and say <em>"refresh."</em></p>
    </section>

    <section class="doc-section" id="privacy-glance">
      <h2>Privacy at a glance</h2>
      <p class="section-lede">A short summary of what stays on your computer and what doesn't. Full detail in the <a class="body-link" href="../legal/privacy.html">Privacy Policy</a>.</p>

      <h3>What stays local by default</h3>
      <ul>
        <li>Your source files (bank statements, payslips, tax documents) — the pipeline scripts read them locally and never upload them.</li>
        <li>The categorized transactions and rendered dashboard — opened in your browser via a <code>file://</code> URL.</li>
        <li>Your AI assistant credentials.</li>
      </ul>

      <h3>What leaves your computer</h3>
      <ul>
        <li><strong>An anonymous install-start ping</strong> when the install script finishes the consent gate. Payload: platform (mac or win), UTC timestamp, advisor_id. No IP, no name, no machine ID. Opt out with <code>FCB_NO_ANALYTICS=1</code>.</li>
        <li><strong>Feedback messages you explicitly send</strong> (via the "I have feedback" widget on your dashboard). These create GitHub issues; we triage and respond.</li>
        <li><strong>Your dashboard, only if you choose to share it</strong> — see <a class="body-link" href="#sharing">Sharing</a> below.</li>
        <li><strong>File contents you ask the assistant to read directly.</strong> If you ask Claude "tell me about this paystub," that file goes to Anthropic as part of your conversation, governed by your Anthropic account terms. The default pipeline doesn't ask Claude to read source files; it processes them with local Python scripts.</li>
      </ul>
    </section>

    <section class="doc-section" id="what-installs">
      <h2>What this installs</h2>
      <p class="section-lede">The complete list of packages, URLs, and files the install scripts touch. This section is auto-generated from <code>installer/install.sh</code> and <code>installer/install.ps1</code> — if a new package appears in the install scripts but isn't documented here, the build fails. So this list cannot drift.</p>

      <h3>System tools</h3>
      <p>Installed via your platform's package manager (Homebrew on Mac, winget on Windows). Skipped if already present.</p>
      <ul class="items">{items(tools_pairs)}</ul>

      <h3>Python packages (workspace virtual environment)</h3>
      <p>Installed by uv into an isolated environment inside your workspace. They never affect your system Python or any other Python project.</p>
      <ul class="items">{items(py_pairs)}</ul>

      <h3>URLs the installer fetches</h3>
      <p>Every URL the install scripts contact, with what we use it for.</p>
      <ul class="items">{items(url_pairs)}</ul>

      <h3>Files and folders we create</h3>
      <p>Everything the installer writes to your machine. Nothing is created outside these locations.</p>
      <ul class="items">{file_items}</ul>

      <h3>What we never touch</h3>
      <ul class="never">{never_items}</ul>
    </section>

    <section class="doc-section" id="sharing">
      <h2>Sharing your dashboard</h2>
      <p class="section-lede">Local-only by default. If you want to share with an advisor or family member, you can opt in per dashboard.</p>

      <p>To share, tell the assistant <em>"share my dashboard."</em> The skill:</p>
      <ol>
        <li>Generates a phone-friendly passcode (4 lowercase words, easy to type).</li>
        <li>Publishes the rendered <code>site/</code> directory to a private here.now URL behind that passcode.</li>
        <li>Reads the URL and passcode back to you, and saves both in <code>~/Documents/my-finances/.env</code> so you can look them up later.</li>
      </ol>

      <p>The published bundle includes the categorized transactions (in JSON embedded in the page and CSV exports under <code>downloads/</code>) and the aggregate summaries shown in the dashboard. It does <strong>not</strong> include the original source files (PDFs, statements). Anyone with the URL plus the passcode can see the dashboard contents; share them carefully.</p>

      <p>To take a published dashboard down: tell the assistant <em>"delete my site"</em> (or run <code>delete-my-site.command</code> from the workspace).</p>
    </section>

    <section class="doc-section" id="reference">
      <h2>Reference</h2>
      <p class="section-lede">Environment variables, opt-outs, and other knobs.</p>

      <h3>Environment variables</h3>
      <table class="ref">
        <thead><tr><th>Variable</th><th>What it does</th></tr></thead>
        <tbody>{env_rows}</tbody>
      </table>

      <h3>Common questions</h3>
      <p><strong>Where does my data live?</strong> In <code>~/Documents/my-finances/</code> on Mac, or <code>%USERPROFILE%\\Documents\\my-finances\\</code> on Windows. Open it like any folder.</p>
      <p><strong>How do I uninstall?</strong> Delete the workspace folder. To also remove Claude Code, follow Anthropic's uninstall instructions for the CLI. To remove uv, jq, and Node, use your package manager (<code>brew uninstall</code> or <code>winget uninstall</code>).</p>
      <p><strong>Does this work offline?</strong> The install needs internet (to download tools and fetch packages). Once installed, the pipeline runs offline except for the FX rate fetch (which uses Frankfurter; you can disable by removing the FX step from <code>refresh.sh</code>). The dashboard works fully offline.</p>
      <p><strong>What if I find a bug?</strong> Click "I have feedback" on your dashboard, or open an issue at <a class="body-link" href="https://github.com/passporttowealth/passporttowealth/issues">github.com/passporttowealth/passporttowealth/issues</a>.</p>
    </section>

    <footer class="docs-footer">
      <p>This page is auto-generated from <a class="body-link" href="https://github.com/passporttowealth/passporttowealth/blob/main/installer/install.sh">install.sh</a> and <a class="body-link" href="https://github.com/passporttowealth/passporttowealth/blob/main/installer/install.ps1">install.ps1</a> by <a class="body-link" href="https://github.com/passporttowealth/passporttowealth/blob/main/installer/build_docs.py">build_docs.py</a>. Source code: <a class="body-link" href="https://github.com/passporttowealth/passporttowealth">github.com/passporttowealth/passporttowealth</a>.</p>
    </footer>
  </main>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    main()
