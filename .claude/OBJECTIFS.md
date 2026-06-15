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

## Critères d'acceptation

_(pour chaque objectif ci-dessus : comment vérifier automatiquement qu'il est atteint — tests, commande à exécuter, comportement observable)_
