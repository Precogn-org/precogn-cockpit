#!/usr/bin/env bash
# Offline smoke checks only; does not send messages to Claude or alter user data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

bash -n "$ROOT/bin/boss-ask.sh"
bash -n "$ROOT/bin/boss-attendre.sh"
PYTHONPYCACHEPREFIX="$TMP/pycache" python3 -m py_compile "$ROOT/bin/canal_boss.py" "$ROOT/bin/session-bus.py"

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

export COCKPIT_BUS_DIR="$TMP/bus"
python3 "$ROOT/bin/session-bus.py" register gpt-main "ChatGPT main" --kind chatgpt >"$TMP/register1.out"
python3 "$ROOT/bin/session-bus.py" register claude-v00 "Claude V00" --kind claude-code >"$TMP/register2.out"
MSG_ID="$(python3 "$ROOT/bin/session-bus.py" send gpt-main claude-v00 "Review the design." )"
python3 "$ROOT/bin/session-bus.py" inbox claude-v00 --pending >"$TMP/inbox.out"
grep -q "$MSG_ID" "$TMP/inbox.out"
grep -q 'Review the design.' "$TMP/inbox.out"
python3 "$ROOT/bin/session-bus.py" ack claude-v00 "$MSG_ID" >"$TMP/ack.out"
python3 "$ROOT/bin/session-bus.py" inbox claude-v00 --pending >"$TMP/empty.out"
grep -q 'inbox empty' "$TMP/empty.out"

echo 'PASS: syntax checks, existing bridge checks, and isolated message-bus checks.'
