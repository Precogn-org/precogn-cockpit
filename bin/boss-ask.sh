#!/bin/bash
# Boss <-> V00 Sous Chef relay.
# Usage: boss-ask.sh "message" -> send to V00 and wait for a response.
#        boss-ask.sh             -> deliver queued outbox messages.
set -u
BASE=${BOSS_BASE:-"${HOME}/.local/share/precogn-cockpit"}
LINK=${COCKPIT_LINK_DIR:-"$BASE/link"}
MAILBOX=${COCKPIT_MAILBOX:-"$BASE/POUR_BOSS.md"}
COCKPIT_CWD=${COCKPIT_CWD:-"$HOME"}
CLAUDE_BIN=${CLAUDE_BIN:-$(command -v claude || true)}
WAIT=${BOSS_ASK_WAIT:-1800}

mkdir -p "$LINK/outbox" "$(dirname "$MAILBOX")"
touch "$MAILBOX"

new_replies() {
  python3 - "$MAILBOX" "$LINK/.vus-pour-boss" "${1:-}" <<'PY'
import sys, re, hashlib, os
mb, st, mode = sys.argv[1], sys.argv[2], sys.argv[3]
try: txt = open(mb, encoding='utf8').read()
except OSError: sys.exit(0)
secs = [p for p in re.split(r'(?m)^(?=## )', txt) if p.startswith('## ')]
h = lambda p: hashlib.md5(p.strip().encode()).hexdigest()
first = not os.path.exists(st)
seen = set(open(st).read().split()) if not first else set()
new = [p for p in secs if h(p) not in seen]
if first: new = secs[:6]
if new:
    print("===== POUR_BOSS.md : %d NOUVELLE(S) réponse(s) de V00 =====" % len(new))
    for p in new: print(p.rstrip() + "\n")
else:
    print("===== POUR_BOSS.md : AUCUNE nouvelle réponse depuis ta dernière relève =====")
deja = [p for p in secs[:3] if p not in new]
if deja:
    print("----- Rappel : les 3 réponses les plus récentes (déjà lues, pour ne rien rater) -----")
    for p in deja: print(p.strip()[:500] + ("..." if len(p.strip()) > 500 else "") + "\n")
if mode != "peek":
    open(st, 'w').write("\n".join(sorted({h(p) for p in secs} | seen)))
PY
}

deliver_outbox() {
  local mode="${1:-}"
  [ -f "$LINK/ETAT-CANAL.md" ] && cat "$LINK/ETAT-CANAL.md" && echo
  new_replies "$mode"
  shopt -s nullglob
  local f files=("$LINK"/outbox/*.md)
  if [ ${#files[@]} -eq 0 ]; then
    echo "===== OUTBOX : vide (aucune note de V00 en attente) ====="
    return
  fi
  mkdir -p "$LINK/outbox/lus"
  for f in "${files[@]}"; do
    echo "===== Note de V00 ($(basename "$f" .md)) ====="
    cat "$f"
    echo
    [ "$mode" = "peek" ] || mv "$f" "$LINK/outbox/lus/"
  done
}

if [ "${1:-}" = "" ]; then
  deliver_outbox
  exit 0
fi

if [ -z "$CLAUDE_BIN" ]; then
  echo "Claude Code CLI introuvable. Définis CLAUDE_BIN ou ajoute claude au PATH." >&2
  exit 127
fi

ID=$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM
REQUEST="$1"
printf '%s\n' "$REQUEST" > "$LINK/inbox-$ID.md"
BEFORE=$(stat -c %Y "$MAILBOX" 2>/dev/null || echo 0)

# The ephemeral relay only sends the request to V00.
# It must NOT write files itself: Claude Code permission prompts made the old
# reply-file protocol unreliable. V00 writes its answer to POUR_BOSS.md.
(
  cd "$COCKPIT_CWD" || exit 1
  timeout 180 "$CLAUDE_BIN" --model haiku -p \
    "Utilise ListAgents, trouve la session dont le nom contient « Sous Chef », puis envoie-lui avec SendMessage EXACTEMENT ce texte, sans rien ajouter :
[BOSS-LINK $ID] Message du Boss : $REQUEST
---
Après réception, V00 doit traiter le message et écrire sa réponse dans $MAILBOX sous un titre contenant exactement « BOSS-LINK $ID ». Ne tente pas d'écrire toi-même ce fichier." \
    --allowedTools ListAgents SendMessage ToolSearch \
    > "$LINK/relay-$ID.log" 2>&1
) &

nudge() {
  (
    cd "$COCKPIT_CWD" || exit 1
    timeout 120 "$CLAUDE_BIN" --model haiku -p \
      "Utilise ListAgents, trouve la session dont le nom contient « Sous Chef », puis envoie-lui avec SendMessage EXACTEMENT ce texte, sans rien ajouter :
RELÈVE — le Boss attend ta réponse à BOSS-LINK $ID. Lis ta boîte aux lettres $MAILBOX et écris ta réponse sous un titre contenant « BOSS-LINK $ID ». Ne lance PAS boss-ask.sh : il est réservé au Boss." \
      --allowedTools ListAgents SendMessage ToolSearch \
      > "$LINK/relay-$ID-releve-$1.log" 2>&1
  ) &
}

echo "Message $ID remis à V00. Attente de sa réponse (max ${WAIT}s)..."

for ((i=0; i<WAIT; i+=5)); do
  if grep -qF "BOSS-LINK $ID" "$MAILBOX" 2>/dev/null; then
    echo "===== Réponse de V00 ====="
    awk -v marker="BOSS-LINK $ID" '
      index($0, marker) {show=1}
      show {print}
      show && NR>1 && /^## / && index($0, marker)==0 {exit}
    ' "$MAILBOX"
    echo
    deliver_outbox peek
    exit 0
  fi
  if [ -e "$LINK/.reveils-actifs" ] && [ "$i" -ge 120 ] && [ $(( (i-120) % 600 )) -eq 0 ]; then nudge "$i"; fi
  sleep 5
done

echo "Pas de réponse de V00 en ${WAIT}s (session occupée ou arrêtée)."
echo "Relance sans argument pour relever outbox : $0"
deliver_outbox peek
