# Runbook — incident en production (déblocage, redéploiement)

Modèle volontairement simple (décidé 2026-09-21) : **un des deux administrateurs nommés
(`Gala-AWS-Administrators`) peut débloquer et agir seul**, sans processus d'approbation
multi-parties. Pas de ticket, pas de second sign-off — la contrainte réelle est déjà
l'authentification (SSO + MFA, session `gala-elevated` de 12 h, voir `docs/aws-access.md`),
pas une validation humaine supplémentaire.

## Ce que `DEPLOYMENT_LOCKED` protège

Une fois un gala ouvert, `registry/<slug>.json` passe à `"deployment_locked": true` et la
config runtime (`/etc/tibillet-gala/<slug>.conf`) a `DEPLOYMENT_LOCKED=true` —
`tools/runtime/preflight.sh` refuse alors tout `deploy-release.sh` (voir
`docs/operations/gala-registry.md`). C'est un garde-fou contre un redéploiement accidentel
pendant l'événement, pas une barrière qui nécessite un comité pour être levée.

## Procédure

1. Un administrateur constate un incident nécessitant un redéploiement (bug bloquant, hotfix
   validé sur une release déjà qualifiée par la pipeline Test).
2. `aws sso login --profile gala-elevated` (session de 12 h, nouvelle MFA seulement si la
   session portail de 14 jours a expiré — voir `docs/aws-access.md`).
3. Backup manuel avant toute action : `sudo /usr/local/lib/tibillet-gala/backup-postgres.sh
   /etc/tibillet-gala/<slug>.conf` (voir `docs/operations/backup-restore.md`).
4. Éditer `/etc/tibillet-gala/<slug>.conf` sur l'EC2 : `DEPLOYMENT_LOCKED=false`.
5. `deploy-release.sh` avec le manifeste de la release déjà validée (jamais une release qui
   n'a pas été qualifiée par la pipeline Test — l'incident ne dispense pas de cette étape).
6. Remettre immédiatement `DEPLOYMENT_LOCKED=true` après le déploiement — ne jamais le
   laisser à `false` au-delà de l'action.
7. Mettre à jour `registry/<slug>.json` : `deployed_release_id`, et une note courte du motif
   de l'incident (pas de format imposé — assez pour qu'un second administrateur comprenne ce
   qui s'est passé s'il regarde plus tard).

## Ce que ce runbook ne couvre pas

- Restauration de données après corruption/perte — voir `docs/operations/backup-restore.md`.
- Rollback vers une release antérieure : même procédure, en pointant `deploy-release.sh` sur
  l'ancien manifeste (toujours un manifeste déjà qualifié par la pipeline Test, jamais un
  rebuild ad hoc pendant l'incident).
