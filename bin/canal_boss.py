#!/usr/bin/env python3
"""Surveille le canal Boss <-> V00 (lecture seule sur POUR_BOSS.md et l'outbox).

- Boss -> V00 : un link/inbox-<id>.md sans titre "BOSS-LINK <id>" dans POUR_BOSS.md
  apres RAPPEL_MIN minutes -> un rappel "RELEVE" a V00 ; apres ALERTE_MIN -> alerte a V01.
- V00 -> Boss : une note de link/outbox/*.md non relevee depuis OUTBOX_MIN minutes
  -> alerte a V01 (qui previent the project owner, ChatGPT ne pouvant pas etre reveille).
Jamais de touches tmux, jamais boss-ask.sh, aucune ecriture dans POUR_BOSS.md.
Etat (anti-doublon) : ~/.local/state/precogn-cockpit/watch-state.json (configurable via CANAL_STATE)
"""
import fcntl, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(os.environ.get("CANAL_BASE", str(Path.home() / ".local/share/precogn-cockpit")))
LINK = Path(os.environ.get("COCKPIT_LINK_DIR", str(BASE / "link")))
MAILBOX = Path(os.environ.get("COCKPIT_MAILBOX", str(BASE / "POUR_BOSS.md")))
STATE_DIR = Path(os.environ.get("CANAL_STATE", str(Path.home() / ".local/state/precogn-cockpit")))
BOSS_CWD = os.environ.get("CANAL_BOSS_CWD", str(Path.home()))
RAPPEL_MIN = float(os.environ.get("CANAL_RAPPEL_MIN", "10"))
ALERTE_MIN = float(os.environ.get("CANAL_ALERTE_MIN", "30"))
OUTBOX_MIN = float(os.environ.get("CANAL_OUTBOX_MIN", "30"))
FENETRE_H = float(os.environ.get("CANAL_FENETRE_H", "24"))
DRY = "--dry" in sys.argv
PASSIF = not (LINK / ".reveils-actifs").exists()
CLAUDE = os.environ.get("CLAUDE_BIN", shutil.which("claude") or "claude")


def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line)
    with open(STATE_DIR / "canal-boss.log", "a") as f:
        f.write(line + "\n")


def envoyer(cible, texte):
    """Message fixe (aucun contenu du Boss) livre par SendMessage via un relais haiku."""
    if DRY:
        log(f"[dry] -> {cible}: {texte[:90]}")
        return True
    consigne = (
        f"Utilise ListAgents, trouve la session dont le nom contient « {cible} », puis envoie-lui "
        f"avec SendMessage EXACTEMENT ce texte, sans rien ajouter :\n{texte}"
    )
    try:
        r = subprocess.run(
            ["timeout", "150", CLAUDE, "--model", "haiku", "-p", consigne,
             "--allowedTools", "ListAgents", "SendMessage", "ToolSearch"],
            cwd=BOSS_CWD, capture_output=True, text=True, timeout=170)
        ok = r.returncode == 0 and "envoy" in r.stdout.lower()
        log(f"envoi -> {cible}: {'OK' if ok else 'ECHEC'} {r.stdout.strip()[:100]!r}")
        return ok
    except Exception as e:
        log(f"envoi -> {cible}: ERREUR {e}")
        return False


def session_boss():
    """Find the interactive Boss session by its configured working directory."""
    try:
        if os.environ.get("CANAL_AGENTS_FILE"):
            L = json.load(open(os.environ["CANAL_AGENTS_FILE"]))
        else:
            r = subprocess.run([CLAUDE, "agents", "--json"], cwd=BOSS_CWD,
                               capture_output=True, text=True, timeout=40)
            L = json.loads(r.stdout)
    except Exception as e:
        log(f"liste des sessions illisible: {e}")
        return None
    for a in L:
        if a.get("cwd") == BOSS_CWD and a.get("kind") == "interactive" and a.get("name"):
            return a["name"]
    return None


def injecter_boss(state, boite):
    """V00 -> Boss : prevenir la session Boss (si connectee) des nouvelles sections de POUR_BOSS.md / notes outbox."""
    secs = [p for p in re.split(r"(?m)^(?=## )", boite) if p.startswith("## ")]
    h = lambda p: hashlib.md5(p.strip().encode()).hexdigest()
    if "boss_notif" not in state:
        state["boss_notif"] = [h(p) for p in secs]
        log(f"init injection Boss : {len(secs)} sections existantes marquees deja vues")
        return
    vus = set(state["boss_notif"])
    try:  # ce que le Boss a deja lu a sa releve (meme calcul d'empreinte que boss-ask.sh)
        vus |= set((LINK / ".vus-pour-boss").read_text().split())
    except OSError:
        pass
    nouvelles = [p for p in secs if h(p) not in vus]
    notes = [f.name for f in sorted((LINK / "outbox").glob("*.md")) if f.name not in state.setdefault("boss_notes", [])]
    if not nouvelles and not notes:
        return
    nom = session_boss()
    if not nom:
        cle = f"{len(nouvelles)}/{len(notes)}"
        if state.get("boss_absent_log") != cle:  # une ligne par changement, pas toutes les 5 min
            log(f"Boss absent : {len(nouvelles)} section(s) non lues a la releve et {len(notes)} note(s) en attente")
            state["boss_absent_log"] = cle
        return
    titres = [re.sub(r"[^\w \-—:./«»()]", "", p.splitlines()[0][3:])[:90] for p in nouvelles[:5]]
    texte = ("RELÈVE — V00 a répondu. Lance boss-ask.sh sans argument pour lire. "
             f"Nouvelles réponses : {len(nouvelles)} ; notes outbox : {len(notes)}. Titres : " + " | ".join(titres))
    if envoyer(nom, texte):
        state["boss_notif"] = sorted(vus | {h(p) for p in nouvelles})
        state["boss_notes"] = state["boss_notes"] + notes


def ecrire_etat(boite, now):
    """Fichier d'etat lisible (aucun envoi) : messages sans reponse, notes non relevees."""
    L = ["# ETAT DU CANAL Boss <-> V00 (mis a jour " + time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(now)) + ")", ""]
    sans = []
    for f in sorted(LINK.glob("inbox-*.md")):
        ident = f.stem[len("inbox-"):]
        age = (now - f.stat().st_mtime) / 60
        if age <= FENETRE_H * 60 and f"BOSS-LINK {ident}" not in boite:
            sans.append(f"- {ident} : sans reponse depuis {int(age)} min")
    notes = [f"- {f.name} : en attente depuis {int((now - f.stat().st_mtime) / 60)} min"
             for f in sorted((LINK / "outbox").glob("*.md"))]
    L += ["Messages du Boss sans reponse (24 h) : " + (str(len(sans)) if sans else "aucun")] + sans
    L += ["", "Notes pour le Boss non relevees : " + (str(len(notes)) if notes else "aucune")] + notes
    (LINK / "ETAT-CANAL.md").write_text("\n".join(L) + "\n", encoding="utf8")


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    sp = STATE_DIR / "watch-state.json"
    state = json.loads(sp.read_text()) if sp.exists() else {"rappel": {}, "alerte": {}, "outbox": {}}
    boite = MAILBOX.read_text(encoding="utf8", errors="replace") if MAILBOX.exists() else ""
    now = time.time()
    ecrire_etat(boite, now)
    if PASSIF:
        return

    for f in sorted(LINK.glob("inbox-*.md")):
        ident = f.stem[len("inbox-"):]
        age = (now - f.stat().st_mtime) / 60
        if age > FENETRE_H * 60 or f"BOSS-LINK {ident}" in boite:
            continue
        if age >= RAPPEL_MIN and ident not in state["rappel"]:
            texte = (f"RELÈVE — le message du Boss {ident} n'a pas de réponse depuis {int(age)} min. "
                     f"Lis ta boîte {MAILBOX} et réponds sous un titre contenant « BOSS-LINK {ident} ». "
                     "Ne lance PAS boss-ask.sh : il est réservé au Boss. (Contrôle automatique du canal.)")
            if envoyer("Sous Chef", texte):
                state["rappel"][ident] = int(now)
        if age >= ALERTE_MIN and ident not in state["alerte"]:
            texte = (f"ALERTE CANAL BOSS→V00 : le message {ident} n'a toujours pas de réponse de V00 "
                     f"après {int(age)} min (rappel envoyé). Préviens le propriétaire du projet : V00 attend peut-être une autorisation.")
            if envoyer("Contrôle VPS", texte):
                state["alerte"][ident] = int(now)

    for f in sorted((LINK / "outbox").glob("*.md")):
        age = (now - f.stat().st_mtime) / 60
        if age >= OUTBOX_MIN and f.name not in state["outbox"]:
            texte = (f"ALERTE CANAL V00→BOSS : la note « {f.name} » attend dans l'outbox depuis {int(age)} min, "
                     "non relevée par le Boss. Demande au propriétaire du projet d'écrire « relève » au Boss dans ChatGPT.")
            if envoyer("Contrôle VPS", texte):
                state["outbox"][f.name] = int(now)

    injecter_boss(state, boite)
    sp.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
