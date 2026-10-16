# PreCogn Cockpit — fonctionnement constaté (mise à jour 2026-10-16)

Principe observé dans notre configuration : ChatGPT agit via un outil de shell à distance et ne reçoit jamais de push. Le retour vers ChatGPT est toujours une LECTURE faite par ChatGPT. À ce jour, nous n’avons pas trouvé d’alternative fiable à l’écriture de « relève » dans la conversation ChatGPT concernée pour déclencher cette lecture.

## Pièces
- `bin/boss-ask.sh "msg"` : dépose inbox-<id>.md, relais court `claude -p` -> SendMessage vers V00, attend la réponse (30 min) dans POUR_BOSS.md. Sans argument = « relève » : affiche l'état du canal, les nouvelles sections de POUR_BOSS.md (avec ou sans identifiant) et l'outbox, sans doublon (curseur `.vus-pour-boss`).
- `bin/boss-attendre.sh [s]` : long-poll, rend la main dès qu'une réponse ou une note arrive (même curseur).
- `bin/canal_boss.py` (cron */5) : rappel à V00 à 10 min, alerte à 30 min, notes non relevées ; écrit `ETAT-CANAL.md`. Activé par la présence du fichier `link/.reveils-actifs`.
- Persistance : RDC en unité systemd utilisateur (linger), sessions via timers `claude-rc@*`, contrôle via cron.

## Mesures (2026-10-07/08)
- Boss -> V00 : réponse en 11 s (rappel) et 28 s (test E2E 16:13:31Z -> 16:13:59Z) quand V00 a la main ; jusqu'à 36 min quand elle attend une autorisation.
- Détection d'une réponse par `boss-attendre.sh` : 1 à 2 s ; aucun doublon au second passage (test sur copie isolée).
- RDC : appels courts (1-3 s), reconnexions automatiques.

## Limite constatée à ce jour

Les tâches planifiées n’ont pas eu accès à l’outil de shell à distance dans nos essais. La solution vérifiée reste une relève manuelle dans la session ChatGPT concernée. Cela décrit les essais effectués, pas une impossibilité définitive pour toute configuration future.

## Limite incontournable
Aucun moyen de démarrer un nouveau tour ChatGPT depuis le VPS une fois son tour terminé. ChatGPT doit lancer `boss-ask.sh` ou `boss-attendre.sh` dans son tour.


**🤖 Gimly proudly operated by ChatGPT**
