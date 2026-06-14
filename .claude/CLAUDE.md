## Délégation locale via Ollama

Un modèle local (`qwen3:8b`, ~5.2GB) est disponible via les outils MCP `mcp__ollama__*`.
Utilise-le pour déléguer les tâches mécaniques suivantes afin d'économiser des tokens :

- Génération de tests unitaires répétitifs
- Reformatage et renommage de variables
- Extraction et transformation de données (JSON, YAML, .env)
- Génération de docstrings et commentaires
- Recherche/remplacement répétitif dans des fichiers (patches, configs Docker Compose)
- Tout ce qui est mécanique et ne demande pas de raisonnement complexe

Pour ces tâches, appelle `mcp__ollama__ollama_generate` ou `mcp__ollama__ollama_chat` avec `model: "qwen3:8b"`.
Garde ton propre raisonnement pour la planification, l'architecture des services (Fedow/Lespass/Laboutik), Traefik et les décisions complexes.

## Code sensible — pas de délégation sans relecture complète

Fedow gère les transactions monétaires et l'intégration Stripe ; Lespass gère l'authentification et les comptes membres. Pour toute modification touchant ces domaines, ne délègue pas au modèle local sans relire intégralement le diff généré ensuite — les tests ne suffisent pas à garantir la sécurité/correction de ce type de code.

## Périmètre du repo

On travaille uniquement sur ce repo. Ne crée pas et ne modifie pas un autre repo — y compris le mécanisme de Dockerfile d'extension (`FROM tibillet/...` + `build:`) évoqué pour la version "grosse gala". C'est un mécanisme de dernier recours : à n'utiliser que si une modification s'avère impossible autrement via les patches/volumes existants, et seulement après avoir prévenu l'utilisateur et obtenu sa confirmation.

## Accès à la VM de prod (galas-am-aix.rezal.fr)

La VM est accessible via `ssh MACHINE-Guinche-Main` (alias défini dans `~/.ssh/config` de l'utilisateur — IP et clé ne sont pas dans ce repo).

Mon rôle sur cette VM est **diagnostic uniquement** : lire les logs (`docker compose logs`), vérifier l'état des containers (`docker compose ps`), inspecter la config déployée. Je ne modifie pas de fichiers directement sur la VM — si je trouve un bug, je corrige dans ce repo en local, on commit/push, et la VM se met à jour via le mécanisme de déploiement (git pull + docker compose pull/up). Exception : déclencher manuellement le script de mise à jour sur la VM si nécessaire.

L'utilisateur ne se SSH plus lui-même sur cette machine — c'est moi qui m'en occupe quand il y a besoin de diagnostiquer/agir dessus.

## Fichiers partagés `.claude/`

- `.claude/OBJECTIFS.md` : objectifs vérifiables du projet (pour le fonctionnement en `/loop`). À consulter/mettre à jour en début et fin de tâche.
- `.claude/NOTES.md` : découvertes techniques importantes sur ce projet (comportements non documentés, intégrations externes). Avant de creuser longtemps sur un problème, vérifier si une entrée existe déjà ici. Après une découverte coûteuse, l'ajouter ici (en plus de la mémoire personnelle, voir `~/.claude/CLAUDE.md`).

Ces fichiers sont commités avec le repo — contrairement à la mémoire personnelle de Claude, ils sont partagés avec toute personne travaillant sur le projet.
