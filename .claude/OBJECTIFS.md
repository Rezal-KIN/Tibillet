# Objectifs du projet

Objectifs vérifiables du projet, pensés pour permettre un fonctionnement en `/loop` (Claude travaille de manière autonome avec un minimum d'arbitrage manuel). Un objectif n'est utile pour `/loop` que s'il est vérifiable automatiquement (tests, critères d'acceptation explicites) — sinon Claude boucle sur des hypothèses non confirmées.

## En cours

- **Stack de preview V2 (alpha)** (`Lespass-v2/`) : faire booter la branche `origin/V2` (pin
  `bc681a34fb1d08c3ba3fdd715d529742b797388e`) "vanilla" sur une DB neuve, isolée de la prod.
  Critère : `docker compose -f Lespass-v2/docker-compose.yml ps` montre tous les conteneurs
  `lespass_v2_*` `Up`, et `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/` (via
  tunnel SSH sur la VM) renvoie 200/302 (pas 500). Corriger les erreurs au démarrage au fil de
  l'eau (variables d'env manquantes, imports, migrations d'apps secondaires) — branche alpha,
  des correctifs sont attendus. Voir `.claude/NOTES.md` pour le contexte complet.
- Porter ensuite progressivement nos features V1 (`custom_patches/` historiques : refund local,
  balance_total, multi-cashless onboarding, qr_card_landing) vers cette base V2 une fois stable —
  tâche distincte, après que le stack boote proprement.
- **Plateforme AWS Gala** (`infra/`, `tools/runtime/`, `buildspec/`, `systemd/`) : infra
  Terraform, scripts runtime, accès SSO portable et pipelines Test/Production. Voir
  `infra/README.md` pour la carte des fichiers et l'ordre d'exécution.
  - **Pinning d'image release — résolu (2026-09-21)**. `COMPOSE_FILES` supporte des groupes
    fusionnés (`a.yml;a.release.yml:b.yml;b.release.yml`, voir
    `tools/runtime/lib.sh:compose_group_args`) et chaque service a son
    `docker-compose.release.yml` (`Fedow/`, `Laboutik/`, `traefik/`, `Lespass/` — ce dernier
    avec `build: !reset null`). Vérifié par `docker compose config` sur les 4 paires. Voir
    `.claude/NOTES.md`, entrée "Pipeline delivery".
  - **Environnement de test permanent — résolu (2026-09-21)** : pas de second Organization/
    Identity Center (impossible — singleton par compte AWS). Le "environnement de test
    permanent" se réalise via (a) la pipeline `tibillet-gala-test` déjà toujours présente une
    fois `enable_delivery_platform=true`, et (b) une entrée dédiée dans `var.galas` pour un
    gala de preview permanent (domaine `dev.<domaine-gala>`, voir `infra/README.md`
    "Conventions de nommage"), le tout dans **une seule** application Terraform
    (`environment = "production"` pour le control-plane du compte). Pas de duplication de
    state/backend pour ça.
  - **Préconditions levées (2026-09-21)** : account ID (318629836660) et e-mail propriétaire
    (kin.rezal@gmail.com), deuxième administrateur (Thomas Tabaczka,
    thomas.tabaczka@ensam.eu — e-mail temporaire, à mettre à jour), domaines chez OVH (accès
    utilisateur confirmés), accès à l'Organization confirmés, fork sous le GitHub org
    `Rezal-KIN` (gouvernance = l'utilisateur). Reste ouvert : nom/prénom du premier
    administrateur (le compte est à son nom mais pas encore précisé), et le chiffrage exact
    de la politique de rétention légale (voir échange du 2026-09-21 — comptable de
    l'association à consulter pour un chiffre définitif ; défaut actuel
    `backup_retention_days = 30` dans `infra/terraform/variables.tf`, à distinguer de la
    rétention comptable/fiscale des exports FEC qui n'est pas dans ce mécanisme).
  - Reste à écrire : `docs/operations/incident.md` (déblocage `DEPLOYMENT_LOCKED` en
    self-service par un administrateur, sans processus d'approbation multi-parties — décidé
    2026-09-21) et `docs/operations/v2-qualification.md` (pas urgent, confirmé).

## Critères d'acceptation

_(pour chaque objectif ci-dessus : comment vérifier automatiquement qu'il est atteint — tests, commande à exécuter, comportement observable)_
