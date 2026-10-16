#!/usr/bin/env bash
# Offline smoke checks only; does not send messages to Claude or alter user data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

bash -n "$ROOT/bin/boss-ask.sh"
bash -n "$ROOT/bin/boss-attendre.sh"
PYTHONPYCACHEPREFIX="$TMP/pycache" python3 -m py_compile "$ROOT/bin/canal_boss.py"

BOSS_BASE="$TMP/cockpit" CLAUDE_BIN=/bin/true bash "$ROOT/bin/boss-ask.sh" >"$TMP/ask.out"
grep -q 'AUCUNE nouvelle réponse' "$TMP/ask.out"
grep -q 'OUTBOX : vide' "$TMP/ask.out"

BOSS_BASE="$TMP/cockpit" CLAUDE_BIN=/bin/true bash "$ROOT/bin/boss-attendre.sh" 1 >"$TMP/wait.out"
grep -q 'Rien de nouveau' "$TMP/wait.out"

CANAL_BASE="$TMP/cockpit" \
CANAL_STATE="$TMP/state" \
CANAL_BOSS_CWD="$TMP" \
CLAUDE_BIN=/bin/true \
python3 "$ROOT/bin/canal_boss.py" --dry

echo 'PASS: syntax checks and isolated offline smoke checks.'
