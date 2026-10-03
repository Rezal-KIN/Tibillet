# G — Surcharge du serializer Fedow retirée

- **Origine** : `a7e496ce` (17 mai 2026), importée dans le fork par `bc5b1a85`.
- **Décision** : retirer G et reprendre le fonctionnement TiBillet exact.
- **Retrait local** : suppression de la copie `custom_patches/fedow_core/serializers.py`
  et de son montage dans `deploy/Fedow/docker-compose.yml`.

## Personnalisation retirée

Cette ancienne copie réparait un utilisateur existant sans portefeuille et
créait une transaction FIRST à zéro pour un actif dont le journal était vide.
Elle remplaçait aussi l'ensemble des autres serializers par une ancienne version,
sans certaines protections de recharge, fusion et détachement de carte de la
référence actuelle. Les régressions de recharge sont conservées dans
l'[investigation initiale](../audits/2026-10-03-fork/INVESTIGATION.md).

## Retour au standard

Fedow utilise maintenant le fichier inclus dans son image. Aucune fonction
équivalente n'a été réécrite et aucune réparation de remplacement n'est ajoutée.
La référence de release est `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c`,
image `tibillet/fedow@sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83`.
Elle est enregistrée dans `deploy/source/image-sources.json` ; la pipeline charge
les images immuables du manifeste de release. Le Compose lancé seul avec son
défaut `latest` n'atteste pas cette référence.

L'archive originale est vérifiée par SHA-256 avant la comparaison. Le vérificateur
du dossier contrôle l'absence du montage et de la copie active ; le résultat
identifie le fichier natif. Le mécanisme de publication des sources conserve
également ce serializer upstream, sans remplacement.

La création normale d'un utilisateur conserve son portefeuille ; la création
d'un actif conserve son token et son FIRST natifs. Les anciennes données
incomplètes ne sont plus réparées silencieusement à l'occasion d'une requête.
Leur présence effective dans la base d'Aix reste à examiner lors du contrôle
ultérieur en lecture seule. Aucun solde, journal, utilisateur ou actif de
production n'a été modifié et aucune migration de base n'a été exécutée.

## Vérifications locales

[G-verification-results.json](G-verification-results.json) conserve la nouvelle
exécution des neuf scénarios natifs et des neuf scénarios de l'ancienne copie.
Les sondes originales et leurs résultats d'audit restent inchangés.

- Recharge nominale : crédit attendu de 1 000 centimes de test.
- Échec avant REFILL local ou Stripe : aucune CREATION ni modification de solde
  persistante ; la nouvelle tentative aboutit.
- Deux validations simultanées du même checkout : une seule paire CREATION/REFILL,
  client à 1 000 et émetteur à zéro. La contrainte refuse le worker concurrent.
- Entrelacement de transactions, actif archivé, VOID multi-lieux, checkout NULL
  anormal et deux factures sans session : résultats natifs attendus vérifiés.
- Création native d'utilisateur et répétition : même portefeuille.
- Création native d'actif : un FIRST et un token de valeur zéro.

Ces vérifications utilisent Django 4.2.30 et PostgreSQL 15.18 locaux ; le Compose
déclare PostgreSQL 13. Les appels externes sont interdits. Ce sont des exécutions
des modèles/serializers réels avec des données synthétiques, pas un test de
charge, de signature HTTP, de webhook Stripe complet ou de caisse déployée.

Pour reproduire la comparaison, préparer les sources et la base éphémère selon
le [guide des sondes](../audits/2026-10-03-fork/probes/README.md), puis placer
la copie historique sous un répertoire de comparaison :

```sh
mkdir -p .context/g-rollback-check/legacy-deployment/deploy/Fedow/custom_patches/fedow_core
git show 9a5840de:deploy/Fedow/custom_patches/fedow_core/serializers.py > .context/g-rollback-check/legacy-deployment/deploy/Fedow/custom_patches/fedow_core/serializers.py
```

Utiliser ce répertoire comme `AUDIT_REPO_ROOT` dans la sonde originale. La variante
`upstream` utilise directement le fichier natif vérifié ; `overlay` utilise
seulement la copie historique pour démontrer la différence.

## Conditions d'une éventuelle réintroduction

Établir d'abord le besoin réel et l'état des données. Vérifier les mécanismes
natifs d'installation/réparation. Ne pas réintroduire la copie complète : toute
exception demandée doit être limitée, documentée et testée avec les protections
de transaction natives conservées.
