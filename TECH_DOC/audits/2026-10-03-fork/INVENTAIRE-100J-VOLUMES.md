# Inventaire des reprises 100J et des montages applicatifs

État du code examiné le 3 octobre 2026. Ce document permet de choisir les éléments à conserver ou retirer. Aucun rollback ni déploiement n'est exécuté par cet inventaire.

## Références et portée

- Le fork Lespass part du contenu `fd768089` / `f0f0d820`, identique ; état de comparaison `origin/main@84982241`.
- Les quatre stacks définies pour le runtime courant sont `deploy/{traefik,Fedow,Laboutik,Lespass}`. Les Compose `*.release.yml` fixent les images ; ils ne changent pas les montages.
- Le relevé couvre les fichiers versionnés. Aucun nouvel accès à Docker/SSH en production : les données de prix, réglages et permissions effectivement présents dans une instance ne sont pas déduits de la seule présence du code.
- L'inventaire historique des 100J du 22 septembre est dans `deploy/docs/platform/tibillet100j-customizations-inventory.md`. Le suivi de portage du 26 septembre est un document historique : ses mentions du bouton de recharge encore masqué ne décrivent pas l'état actuel.
- `deploy/Laboutik_100-jours-225/`, `deploy/Lespass-v2/` et `deploy/Lespass/legacy-100j-qr-flow/` sont des archives/héritages, exclus du runtime Gala courant. Les montages de l'ancien Compose archivé ne sont pas ceux de la nouvelle instance.

## Choix possibles, avec commit d'introduction

Les identifiants A–L sont des éléments de sélection pour un futur retour arrière. Un fichier entier peut servir plusieurs fonctions : retirer une fonction et retirer son montage sont deux modifications différentes.

| ID | Élément | Origine et état | Livraison actuelle | Introduction et effet d'un retrait ciblé |
| --- | --- | --- | --- | --- |
| A | QR : inscription avec email/prénom/nom, liaison carte/wallet, accès à la recharge | Réimplémentation du parcours 100J avec contrôle email avant liaison pour un compte existant | **Intégré à l'image Lespass**, `BaseBillet/views_qr_card.py`, `BaseBillet/urls.py`, `AuthBillet/utils.py`, templates QR et email ; aucun montage Python Lespass | `6a1d7b87` (#71, 26/09). Retirer les routes, vues et templates ensemble ; conserver les correctifs de logs/CSRF sauf décision séparée. Vérifier les QR imprimés et liens email déjà distribués. |
| B | Guide cashless de l'accueil et bouton adhésion ouvrant la connexion | Repris du rendu public 100J | **Intégré à l'image Lespass**, `BaseBillet/templates/reunion/views/home.html` | `35786671` (#72, 26/09). Retrait essentiellement visuel ; vérifier le CTA adhésion. |
| C | Happy hour : affichage et validation serveur des prix | Héritage Gala/100J. Déjà présent au premier commit historique disponible, pas écrit lors du portage de septembre | **Volumes LaBoutik**, `views.py` + `validators.py`. Prix dans le volume `www/happy_hour_prices.json`, plage par défaut 22:00–23:30 | Historique `30c571bc` (03/05) ; import fork `bc5b1a85` (#1, 21/09). Retirer UI et validation ensemble ; ne pas toucher aux ventes enregistrées ni à la base. |
| D | Limite de deux terminaux sur `caisse`, exclusion du plus ancien, exception nom commençant par `admin` | Même héritage que C | **Volume LaBoutik**, `views.py` | `30c571bc` → `bc5b1a85`. Retirer les appels et gardes liés aux terminaux ; garder le reste de la caisse. |
| E | Tentative d'enregistrement d'une carte inconnue | Même héritage que C ; actuelle gestion d'erreur trop large | **Volumes LaBoutik**, `views.py` + `validators.py` | `30c571bc` → `bc5b1a85`. Le retrait enlève l'enregistrement opportuniste au scan ; vérifier le circuit d'enrôlement normal. |
| F | Synchronisation de monnaie cadeau optionnelle, désactivée par défaut | Même héritage que C | **Volume LaBoutik**, `fedow_api.py`, variable `ENABLE_GIFT_ASSET_SYNC` | `30c571bc` → `bc5b1a85`. Retrouver le comportement upstream peut recréer une monnaie cadeau au bootstrap ; examiner configuration et assets existants avant. |
| G | Création de wallet manquant et bloc FIRST automatique | Ancienne copie Fedow du déploiement Gala. Pas un portage récent depuis le relevé SSH 100J | **Volume Fedow**, `custom_patches/fedow_core/serializers.py` | Historique `a7e496ce` (17/05) ; import `bc5b1a85`. Retirer le montage rend le serializer de l'image ; revoir le bootstrap et utilisateurs sans wallet. Ce fichier porte les régressions de recharge démontrées dans `INVESTIGATION.md`. |
| H | Suivi financier : recharges/dépenses/soldes, graphiques et filtres | Ancienne personnalisation Gala. Fichiers initialement `30c571bc`, puis remaniés jusqu'à `dd707102` (12/05). Les changements 100J non commités du relevé du 22/09 ne sont pas tous repris | **Volumes Fedow**, dashboard `views.py`, `urls.py`, `index.html`, `suivi.html` | Import `bc5b1a85`. Retirer ces quatre montages ensemble rend le dashboard de l'image ; le suivi `/dashboard/suivi/` disparaît. Garder séparément les liens de sources AGPL. |
| I | Configuration Python des deux services | Réglages de déploiement historiques, enrichis depuis ; ce ne sont pas des fonctionnalités 100J | **Volumes**, `deploy/Fedow/settings.py`, `deploy/Laboutik/settings.py` | `30c571bc` → `bc5b1a85`, retouches ultérieures listées dans `file-history.json`. Fedow utilise PostgreSQL via ce fichier : le retirer seul ferait revenir la configuration SQLite de référence. Préparer une configuration équivalente dans l'image avant retrait. |
| J | Installateur LaBoutik reprenable | Correction récente de bootstrap : conserve les appairages et évite les doublons | **Volume**, `deploy/Laboutik/install.py` | `a58a15f8` (#82, 26/09). Retirer rend l'installateur original ; le script de déploiement relance l'installation, donc vérifier les retries/appairages. |
| K | Liens vers les sources AGPL, publics et administratifs | Ajout récent de publication des sources, pas une reprise 100J | **Volumes**, templates `source_templates/`, `admin-templates/`, templates Fedow `base.html`/`public_index.html`, répertoire `source/public` ; aussi liens intégrés Lespass | Première introduction des montages `01ca8349` (#94, 03/10), retouches #95/#98/#100. Garder une offre de sources et un lien accessibles si on retire ces montages, par exemple dans des images construites. |
| L | Configuration Nginx, dont alias LaBoutik `/admin` → `/adminstaff/` | Configuration d'exploitation et ajout demandé pour Aix | **Volumes**, répertoires `nginx/` des trois applications | Répertoires importés `bc5b1a85`, `/source/` en #94, alias admin `1d98cb56` (03/10). Retirer les volumes sans fournir une conf Nginx équivalente peut interrompre les routes et le proxy Django. |

### Preuve de la reprise des fichiers LaBoutik

Les trois fichiers `deploy/Laboutik/{views.py,validators.py,fedow_api.py}` sont identiques aux copies `deploy/Laboutik_100-jours-225/` après retrait des deux nouvelles lignes de notice de licence dans la copie active. Le relevé SSH historique avait établi l'identité de ces copies 100J avec celles du serveur à cette date. Cela établit l'héritage de leur code, pas qui a écrit chaque fonction avant le premier commit disponible.

### Fonctionnalités 100J conservées seulement en archive ou non portées

- Solde total multi-monnaies et demande de remboursement local par IBAN/BIC : non portés dans Lespass actif.
- Ancien login qui connectait aussi un compte existant sur saisie email/scan : non repris tel quel ; A conserve une preuve email pour les comptes existants.
- Endpoint Fedow `register_nfc_card`, outil physique `card_printer/`, nouveaux noms de bars du relevé non commité : non portés dans la stack active.
- Les actions d'adhésion, limites par tarif et accès admin qui existent déjà dans Lespass upstream ne sont pas des ajouts de ce fork.
- L'archive QR exacte a été ajoutée à la lignée actuelle dans `7c475f18` (#2, 22/09). La retirer enlèverait une référence documentaire ; cela ne change pas le runtime.

## Tous les volumes, y compris les données

L'annexe [VOLUMES.md](VOLUMES.md) énumère **47 montages distincts par service**, pour **50 lignes brutes**. Trois lignes LaBoutik (`views.py`, `fedow_api.py`, `validators.py`) sont déclarées deux fois ; cela ne représente pas deux implémentations.

| Volume | Usage et lien avec le code | Retour arrière |
| --- | --- | --- |
| `database/` (3 bases PostgreSQL) | Comptes, cartes, transactions, soldes, configurations | À conserver. Revenir sur le code n'efface pas les données. Aucun rollback de DB proposé ici. |
| `www/` | Médias/fichiers servis, prix happy hour LaBoutik, éventuelles données générées | À conserver ou migrer explicitement. Le JSON de prix fait partie des données, même si la logique C est retirée. |
| `logs/` | Journaux des applications, Nginx, Celery | Indépendant du code métier. Le partage du volume Lespass avec Celery a été ajouté en `e2ad1406` (#59). |
| `backup/`, `ssh/` | Sauvegardes et configuration d'accès pour sauvegardes | Leur présence dans Compose ne prouve pas qu'ils sont utilisés/configurés. Vérifier les tâches de sauvegarde avant retrait. |
| `acme.json` | État des certificats TLS Traefik | À conserver avec la configuration TLS ; aucun fichier de certificat n'est inclus dans ce rapport. |
| `/var/run/docker.sock:ro` | Traefik lit Docker pour découvrir les routes | À conserver tant que ce provider est utilisé, ou préparer une autre configuration de découverte. |
| `nginx/`, `source/public` | Routage et fichiers d'offre de sources | L/K ci-dessus ; peuvent être embarqués dans des images, en maintenant leurs fonctions. |
| Fichiers `.py` et templates ciblés | Remplacent les fichiers inclus dans l'image | C–K ci-dessus. Ce sont les montages à traiter pour que l'image décrive entièrement le code exécuté. |

## Comment préparer le rollback que tu choisiras

1. Choisir les identifiants A–L concernés et préciser si l'objectif est de retirer la fonctionnalité ou seulement d'embarquer son code dans une image.
2. Utiliser le commit d'introduction et son parent pour retrouver le diff exact, puis construire un **nouveau commit ciblé** sur l'état actuel. L'historique et les changements ultérieurs restent disponibles.
3. Pour C–I, ne pas faire un `git revert` global de `bc5b1a85` : ce merge a importé toute l'infrastructure, pas seulement les surcharges. Avant le fork, ces chemins n'existaient pas. Pour rendre le code upstream, retirer les montages sélectionnés et leurs dépendances/configuration, ou reconstruire des images avec des personnalisations minimales.
4. Pour A/J/L, tenir compte des modifications ultérieures des mêmes fichiers et des scripts qui les appellent. Une restauration entière au parent peut réintroduire d'autres erreurs.
5. Tester les parcours concernés sur une stack isolée avec sources/images épinglées, puis vérifier les parcours financiers et les données sur un environnement explicitement choisi avant déploiement.

Un changement d'architecture qui conserve C–H tout en construisant des images personnalisées supprimerait les montages de code sans supprimer ces fonctionnalités. Le rollback métier, lui, rend le comportement de référence et enlève les fonctionnalités choisies.
