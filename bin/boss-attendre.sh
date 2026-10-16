#!/bin/bash
# Attend (long-poll) une nouvelle reponse de V00/V01 pour le Boss, puis l'affiche et rend la main.
# Usage : boss-attendre.sh [secondes_max]   (defaut 600)
# Ne modifie rien d'existant : s'appuie sur boss-ask.sh (sans argument) pour AFFICHER et marquer comme vu.
# Pas de doublon : le curseur est le meme que celui de boss-ask.sh (.vus-pour-boss + outbox/lus).
set -u
BASE=${BOSS_BASE:-"${HOME}/.local/share/precogn-cockpit"}
LINK=${COCKPIT_LINK_DIR:-"$BASE/link"}
MAILBOX=${COCKPIT_MAILBOX:-"$BASE/POUR_BOSS.md"}
ASK=${BOSS_ASK:-"$(dirname "${BASH_SOURCE[0]}")/boss-ask.sh"}
MAX=${1:-600}

nouveau() {
  shopt -s nullglob
  local o=("$LINK"/outbox/*.md)
  [ ${#o[@]} -gt 0 ] && return 0
  python3 - "$MAILBOX" "$LINK/.vus-pour-boss" <<'PY'
import sys, re, hashlib, os
mb, st = sys.argv[1], sys.argv[2]
try: txt = open(mb, encoding='utf8').read()
except OSError: sys.exit(1)
secs = [p for p in re.split(r'(?m)^(?=## )', txt) if p.startswith('## ')]
h = lambda p: hashlib.md5(p.strip().encode()).hexdigest()
if not os.path.exists(st): sys.exit(0)
seen = set(open(st).read().split())
sys.exit(0 if any(h(p) not in seen for p in secs) else 1)
PY
}

echo "En attente d'une nouvelle reponse (max ${MAX}s)..."
for ((i=0; i<MAX; i+=2)); do
  if nouveau; then
    echo "===== Nouvelle reponse detectee apres ${i}s ====="
    "$ASK"
    exit 0
  fi
  sleep 2
done
echo "Rien de nouveau apres ${MAX}s. Relance : $0 [secondes]"
