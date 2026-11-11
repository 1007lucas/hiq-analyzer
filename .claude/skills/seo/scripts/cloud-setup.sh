#!/usr/bin/env bash
# Set up the claude-seo runtime in a Claude Code cloud session, where
# cdn.playwright.dev is blocked but a Chromium build is pre-installed under
# $PLAYWRIGHT_BROWSERS_PATH (/opt/pw-browsers). Installs the Python deps, pins
# the venv's Playwright to the version that matches the pre-installed browser,
# and links that browser into the runtime's managed ms-playwright directory.
# Run from the repository root:  .claude/skills/seo/scripts/cloud-setup.sh
set -euo pipefail
here="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
seo_dir="$(dirname "$here")"
launcher="$here/claude-seo"

"$launcher" setup --skip-browser

browsers="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
venv_py="$seo_dir/.venv/bin/python"
if [[ -d "$browsers" && -x "$venv_py" ]]; then
    # Match Playwright to the pre-installed browser (node's playwright/package.json
    # version is the one the browser was installed for).
    want="$(node -e "console.log(require('playwright/package.json').version)" 2>/dev/null || true)"
    if [[ -n "$want" ]]; then
        "$venv_py" -m pip install --disable-pip-version-check -q "playwright==$want"
    fi
    mkdir -p "$seo_dir/ms-playwright"
    for d in "$browsers"/chromium-* "$browsers"/chromium_headless_shell-* "$browsers"/ffmpeg-*; do
        [[ -d "$d" ]] && ln -sfn "$d" "$seo_dir/ms-playwright/$(basename "$d")"
    done
    "$venv_py" - "$seo_dir/runtime-state.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s["browser_ready"] = True
json.dump(s, open(p, "w"), indent=2, sort_keys=True)
PY
fi
"$launcher" doctor
