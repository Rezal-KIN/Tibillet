# Reproduire les observations locales

Ces sondes exécutent du code de référence et la surcharge actuelle sur des données synthétiques. Elles diagnostiquent des écarts ; leur sortie JSON n'est pas un certificat de conformité. Les échecs simulés et les IntegrityError des workers perdants sont des observations attendues.

## Préparation

Depuis la racine du dépôt, utiliser Python 3.11 et Docker local :

```sh
python3.11 -m venv .context/overlay-investigation/venv
.context/overlay-investigation/venv/bin/pip install -r TECH_DOC/audits/2026-10-03-fork/probes/requirements-observed.txt
python3 TECH_DOC/audits/2026-10-03-fork/probes/prepare_sources.py --destination .context/overlay-investigation
```

`prepare_sources.py` télécharge les deux archives publiques exactes décrites dans le snapshot et vérifie leurs SHA-256 avant extraction. Un cache avec ces mêmes noms évite le téléchargement. Aucun clone mobile de `main` n'est utilisé.

## Fedow avec PostgreSQL local

Créer une base éphémère séparée de toute stack applicative :

```sh
docker run --detach --name luanda-overlay-audit-pg --publish 127.0.0.1::5432 --env POSTGRES_USER=overlay_audit --env POSTGRES_DB=overlay_audit --env POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data postgres:15-alpine
docker port luanda-overlay-audit-pg 5432/tcp
```

L'audit du 3 octobre a utilisé PostgreSQL 15.18. Le port est attribué dynamiquement. Exécuter la sonde avec ce port :

```sh
AUDIT_PG_PORT=$(docker port luanda-overlay-audit-pg 5432/tcp | cut -d: -f2) \
AUDIT_SOURCE_ROOT="$PWD/.context/overlay-investigation" \
AUDIT_REPO_ROOT="$PWD" \
.context/overlay-investigation/venv/bin/python TECH_DOC/audits/2026-10-03-fork/probes/run_fedow_probe.py
```

La sonde utilise exclusivement `127.0.0.1`, la base `overlay_audit`, et le port fourni. Elle migre et **vide cette base de test entre les scénarios**. Elle n'utilise aucun `.env` applicatif ni credential de production. Le JSON nouveau est enregistré sous `.context/overlay-investigation/fedow-results.json` ; le résultat original conservé dans le dossier d'audit reste inchangé.

Elle compare 9 scénarios pour chacune des deux variantes : succès local, échec local, échec Stripe, course de deux validations du même checkout, entrelacement du modèle, champ d'asset archivé, VOID multi-lieux, CREATION FED anormale à checkout NULL, factures avec session vide. Le faux échec du REFILL et le rendez-vous des workers sont injectés ; les requêtes, modèles et écritures PostgreSQL sont réels. Aucun paiement Stripe ne s'exécute.

Supprimer ensuite seulement le conteneur de test créé ci-dessus :

```sh
docker rm --force luanda-overlay-audit-pg
```

## LaBoutik : fonctions avec collaborateurs instrumentés

```sh
AUDIT_SOURCE_ROOT="$PWD/.context/overlay-investigation" \
AUDIT_REPO_ROOT="$PWD" \
.context/overlay-investigation/venv/bin/python TECH_DOC/audits/2026-10-03-fork/probes/run_laboutik_probe.py
```

Cette sonde n'installe pas LaBoutik et n'appelle aucun service. Elle exécute les vraies fonctions isolées avec HTTP/ORM instrumentés ; les décorateurs sont omis. Elle observe notamment les paramètres de timeout, la branche de création de carte sur panne et les retours d'erreur. Le traitement complet de billets et d'adhésions n'est pas validé par cette sonde.

`inventory_mounts.py` sert au relevé des Compose et de leur première apparition dans la lignée du fork. Son exécution après un changement de code actualise `VOLUMES.md`/`volumes.json` : créer un nouvel audit si l'on veut conserver le snapshot courant.
