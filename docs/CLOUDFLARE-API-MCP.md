# Connexion du MCP officiel Cloudflare au Cockpit

**Statut : proposition documentée — OAuth et déploiement non effectués.**

## Service

Serveur officiel Cloudflare API MCP : `https://mcp.cloudflare.com/mcp`

Documentation : https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/

Ce serveur expose les API Cloudflare et leur documentation via MCP. C'est un connecteur d'administration du compte Cloudflare, pas un shell Linux.

## Périmètre et sécurité

Selon les autorisations OAuth accordées, il peut accéder aux ressources Cloudflare autorisées (DNS, Workers, R2, Zero Trust, tunnels et autres API disponibles).

Il ne donne pas de droits root sur le VPS, ne permet pas de lancer `sudo` et ne donne pas accès arbitraire aux fichiers Linux. La délégation d'administration système doit rester un mécanisme distinct, limité dans le temps, approuvé et audité.

Ne pas confondre :
- OAuth Cloudflare MCP : accès aux API Cloudflare autorisées ;
- Cloudflare Access / SSH : contrôle d'accès réseau et authentification ;
- root Linux : privilèges d'administration du système.

## Configuration d'un client MCP compatible

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

Le client doit ensuite effectuer le parcours OAuth dans un navigateur. Le propriétaire du compte Cloudflare choisit et approuve les permissions.

Aucun mot de passe, jeton OAuth, clé API ou secret ne doit être stocké dans Git, dans les arguments de commande ou dans les journaux.

## Règles d'intégration Cockpit

1. Déclarer le serveur comme connecteur externe optionnel `cloudflare-api`.
2. Commencer par les permissions de lecture nécessaires à l'inventaire.
3. Faire approuver OAuth par le propriétaire du compte dans le navigateur du client.
4. Vérifier les comptes, zones et permissions réellement accessibles.
5. Exiger une validation explicite avant toute opération d'écriture.
6. Stocker les jetons dans le coffre sécurisé du runtime, jamais dans le dépôt.
7. Tracer les opérations sans enregistrer de secrets.
8. Documenter révocation et reconnexion.

Un agent utilisant son propre runtime OAuth doit être autorisé selon le modèle de sécurité retenu. Ne pas copier les jetons personnels entre agents. Un éventuel courtier de connexion partagé doit être conçu explicitement et sécurisé.

## Compatibilité

- Claude Code, Codex et autres clients : connexion possible si la version utilisée prend en charge MCP HTTP distant et le parcours OAuth.
- ChatGPT : la connexion d'un serveur MCP personnalisé dépend de l'offre, du workspace et des fonctions activées. Ne pas déclarer ChatGPT connecté sans OAuth achevé et appel de lecture réussi.
- Cockpit : ce connecteur est une capacité externe. Il ne remplace ni le registre des agents, ni le contexte partagé, ni le bus de coordination.

## Tests d'acceptation

- [ ] OAuth approuvé par le propriétaire du compte Cloudflare.
- [ ] Connexion active visible dans le client MCP.
- [ ] Appel de documentation `docs()` réussi.
- [ ] Inventaire en lecture seule limité aux ressources attendues.
- [ ] Permissions vérifiées ; écriture non autorisée refusée.
- [ ] Aucun secret dans Git, logs ou messages.
- [ ] Révocation et reconnexion testées.

## État de réalisation

Cette documentation ne réalise pas elle-même la connexion OAuth et ne modifie aucun service du VPS ou paramètre Cloudflare. Le déploiement dans les runtimes du VPS nécessite un canal d'administration autorisé et vérifiable.

**Décision :** ne pas utiliser le MCP Cloudflare comme substitut à une délégation root temporaire. Cette dernière fera l'objet d'une conception séparée, avec approbation humaine, expiration et audit.
