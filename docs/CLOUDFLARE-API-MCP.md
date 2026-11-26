# Connexion du MCP officiel Cloudflare au Cockpit

**Statut : proposition d'intégration documentée — connexion OAuth et déploiement non effectués.**

## 1. Service à connecter

Le serveur officiel Cloudflare API MCP est :

`https://mcp.cloudflare.com/mcp`

Documentation officielle : https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/

Il expose un accès MCP à l'API Cloudflare et à sa documentation. Il s'agit d'un connecteur d'administration du compte Cloudflare, pas d'un accès shell au VPS.

## 2. Ce que ce MCP permet — et ne permet pas

Il peut, selon les autorisations OAuth accordées, interroger et gérer des ressources Cloudflare : DNS, Workers, R2, Zero Trust, tunnels et autres produits couverts par l'API.

**Il ne donne pas à lui seul les droits root sur Linux.** Il ne permet pas de lire arbitrairement les fichiers du VPS, de lancer `sudo`, ni de se connecter comme `root`. L'administration temporaire du système devra être conçue séparément (broker d'élévation, approbation humaine, droits minimaux, durée limitée, audit et révocation).

Ne pas confondre :
- OAuth Cloudflare MCP : autorise un agent à appeler les API Cloudflare sélectionnées ;
- Cloudflare Access / SSH : contrôle l'accès réseau et l'authentification à une ressource ;
- privilèges Linux root : droits d'administration du système d'exploitation.

## 3. Configuration cliente

Pour un client MCP compatible HTTP distant et OAuth, la configuration de base est :

```json
{
  "mcpServers": {
    "cloudflare-api": {
      "type": "http",
      "url": "https://mcp.cloudflare.com/mcp"
    }
  }
}
```

Le client doit ensuite lancer le parcours OAuth dans un navigateur. L'utilisateur se connecte directement à Cloudflare et sélectionne les permissions qu'il accepte.

Ne jamais placer de mot de passe, jeton OAuth, clé API ou secret dans ce dépôt, dans un fichier partagé non chiffré, dans les arguments de commande ou dans les journaux.

## 4. Politique de connexion Cockpit

1. Ajouter le serveur comme connecteur externe nommé `cloudflare-api`.
2. Démarrer avec les permissions de lecture strictement nécessaires à l'inventaire.
3. Faire effectuer le parcours OAuth par le propriétaire du compte Cloudflare, dans le navigateur du client qui établit la connexion.
4. Vérifier l'identité Cloudflare, les comptes/zones visibles et les permissions réellement accordées.
5. N'autoriser les modifications qu'après validation explicite du périmètre et des scopes.
6. Conserver les jetons dans le magasin sécurisé du client / runtime, jamais dans Git.
7. Tracer les opérations sans journaliser les secrets.
8. Prévoir une révocation OAuth côté Cloudflare et une procédure de reconnexion.

Chaque agent qui utilise son propre runtime OAuth devra être autorisé séparément, sauf si une architecture de courtier de connexion partagée, explicitement conçue et sécurisée, est mise en place. Ne pas copier un jeton utilisateur entre agents.

## 5. Compatibilité des agents

- **Claude Code / Codex / autres clients MCP** : connecter le serveur distant si la version du client supporte HTTP Streamable et OAuth ; suivre la procédure native de ce client.
- **ChatGPT** : la possibilité d'ajouter un serveur MCP distant personnalisé dépend de l'offre, du workspace et des fonctions activées. Ne pas déclarer ChatGPT connecté avant d'avoir effectivement terminé OAuth et validé un appel de lecture.
- **Cockpit** : le connecteur Cloudflare est une capacité externe optionnelle. Il ne devient pas le registre des agents ni le bus de messages Cockpit.

## 6. Tests d'acceptation

Avant de déclarer l'intégration opérationnelle :

- [ ] OAuth terminé par le propriétaire du compte Cloudflare.
- [ ] Le client affiche une connexion active au serveur officiel.
- [ ] Un appel de documentation `docs()` fonctionne.
- [ ] Un inventaire en lecture seule des ressources autorisées fonctionne.
- [ ] Les comptes et zones visibles correspondent au périmètre attendu.
- [ ] Une opération d'écriture non autorisée est refusée.
- [ ] Aucun secret n'est présent dans Git, les logs ou les messages.
- [ ] La révocation OAuth et la reconnexion ont été testées.

## 7. État réel de cette proposition

Cette documentation prépare l'intégration mais ne réalise pas la connexion OAuth et ne modifie pas le VPS. L'autorisation OAuth doit être validée dans le navigateur du propriétaire du compte. Le déploiement sur les runtimes du VPS exige ensuite un canal d'administration autorisé et vérifiable.

**Décision de sécurité :** ne pas utiliser le MCP Cloudflare comme substitut à un mécanisme de délégation root temporaire. Ce mécanisme fera l'objet d'une conception séparée, avec approbation humaine par session, durée d'expiration et audit.
