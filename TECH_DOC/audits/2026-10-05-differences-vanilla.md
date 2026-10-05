# Inventaire complet des différences avec TiBillet vanilla

Cet inventaire décrit les différences du dépôt local au commit `4c6091eb`,
vérifiées le 5 octobre 2026. Il rassemble les personnalisations applicatives,
les écarts hérités, la présentation, le déploiement, les outils et la documentation.
Il ne constate pas l'état actuel d'un serveur. Les retraits locaux précédents
ne sont pas déployés par ce travail.

La liste Git comporte **295 fichiers différents : 280 ajoutés et 15 modifiés**.
Un fichier ajouté sous `deploy/` peut remplacer un fichier natif dans un
conteneur : le statut Git « ajouté » ne signifie donc pas « sans effet sur
l'application ». Les trois fichiers du présent inventaire sont des ajouts
documentaires ultérieurs au commit comparé.

## Références de comparaison

| Application | Référence vanilla retenue |
| --- | --- |
| Lespass | `TiBillet/Lespass@fd7680891c31bbdf6215e7a0750074de89ff5e8e`, base du fork ; même arbre que `f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9` dans l'histoire réécrite |
| Fedow | `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c`, source de l'image épinglée |
| LaBoutik | `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`, source de l'image épinglée |

La comparaison porte sur ces versions fixes, pas sur les branches amont
actuelles. Le catalogue des images et des archives est
[`deploy/source/image-sources.json`](../../deploy/source/image-sources.json).

Annexes : [liste exhaustive des 295 fichiers](2026-10-05-differences-vanilla-fichiers.tsv),
[preuves et montages](2026-10-05-differences-vanilla-preuves.json).
L'[audit initial](2026-10-03-fork/INDEX.md) reste intact.

## Lespass

**16 fichiers applicatifs différents : 10 modifiés, 6 ajoutés.**
Le code Python et les templates ci-dessous sont intégrés à l'image Lespass.

| Différence | Fichiers | Introduction et effet |
| --- | --- | --- |
| A — parcours QR et liaison carte/portefeuille | `BaseBillet/views_qr_card.py`, `BaseBillet/urls.py`, `AuthBillet/utils.py` | Portage ciblé le 26 septembre, `6a1d7b87` ; inscription/connexion, liaison de carte, retour vers la carte ; preuve email avant connexion d'un compte existant ; email personnalisable et indicateur de création de compte |
| A — écrans et email du parcours | `qr_landing.html`, `qr_check_email.html`, `qr_connexion.html` | Nouvelles pages de carte et de confirmation ; email du parcours QR |
| Formulaire d'inscription | `BaseBillet/templates/reunion/views/register.html` | Texte de recharge, jeton CSRF et retrait de logs navigateur contenant l'email |
| Logs des emails | `BaseBillet/tasks.py` | Retrait des liens de connexion complets des logs |
| B — guide de connexion | `BaseBillet/templates/reunion/views/home.html` | Reprise le 26 septembre, `35786671` ; guide en trois étapes et bouton adhésion/connexion |
| Domaine du Gala | `Administration/management/commands/configure_gala_apex.py` | Ajout le 26 septembre, `cb39884d` ; associe le domaine public au tenant Gala, règle les domaines primaires pour les liens et emails |
| Bouton de recharge | `Administration/management/commands/configure_gala_refill.py` | Ajout le 27 septembre, `a9b2ff7f` ; active le champ natif `force_show_refill_button` pour le parcours Fedow/Stripe |
| Transport vers Fedow | `fedow_connect/fedow_api.py` | Ajout le 26 septembre, `ed5cb0c6` ; sous `GALA_LOCAL_FEDOW=1`, utilise le réseau Docker local, avec Host public et signatures conservés |
| Configuration email | `TiBillet/settings.py` | Booléens SMTP TLS/SSL correctement interprétés ; backend email configurable |
| Connexion administrateur | `Administration/admin/site.py` | Ajout le 3 octobre, `1d98cb56` ; formulaire par mot de passe sous `GALA_APEX_TENANT=1` ; dans les autres cas, redirection vers `/?login=1` au lieu de `/` |
| K — liens vers les sources | `Administration/admin/dashboard.py`, `seo/templates/seo/partials/tibillet_community_links.html` | Ajout le 3 octobre ; lien dans l'administration et lien public |

Les chemins complets figurent dans l'annexe TSV et dans
l'[inventaire des cibles applicatives](2026-10-03-etat-actuel.md).

## Fedow

**8 cibles source personnalisées**, dont le template admin partagé avec LaBoutik.
Elles sont apportées par des montages de fichiers ou de répertoires.

| Différence | Sources locales | Effet |
| --- | --- | --- |
| I — base de données | `deploy/Fedow/settings.py` | PostgreSQL remplace SQLite, valeur par défaut de la référence Fedow ; les données ne sont pas converties en retirant le fichier |
| I — autres paramètres | Même fichier | Gestion des hôtes et origines CSRF différente ; répertoire `source_templates` ; browser reload activé en DEBUG |
| H — dashboard Gala | `custom_patches/fedow_dashboard/views.py`, `urls.py`, `index.html`, `suivi.html` | Suivi des recharges, dépenses et soldes ; filtres par période, lieu et bar ; graphiques et rafraîchissement ; accueil personnalisé |
| H — fonctions natives absentes | Les mêmes vues et routes | Les dashboards d'asset et de réseau, dormance, masse monétaire, cycle de vie, courbes temporelles/survie et classements natifs ne sont pas conservés ; anciennes vues d'asset/lieu et organisation du cache différentes |
| K — liens publics des sources | `custom_patches/fedow_dashboard/base.html`, `public_index.html` | Liens ajoutés au footer et à l'accueil public |
| K — lien admin des sources | `deploy/source/admin-templates/admin/base_site.html` | Extension du template admin par le répertoire partagé `source_templates` |

Les personnalisations historiques ont été importées le 21 septembre par
`bc5b1a85` ; les liens K ont été ajoutés le 3 octobre. H conserve les anciens
libellés `PIAN'S`, `oenol'ss` et `shots`. Les limites du suivi en lecture,
notamment les filtres invalides, le rafraîchissement et le coût des requêtes,
sont documentées dans [la vérification G E K H](2026-10-03-suite-G-E-K-H.md).

G a été retiré : le serializer natif des transactions de l'image n'est plus
remplacé par une copie locale.

## LaBoutik

**9 cibles source personnalisées**, dont le template admin partagé avec Fedow.
Les sources locales remplacent des fichiers entiers de l'image.

| Différence choisie ou technique | Sources locales | Effet |
| --- | --- | --- |
| E — enregistrement des cartes inconnues | `deploy/Laboutik/views.py`, `validators.py` | Enregistrement opportuniste au scan ; correction locale du 3 octobre pour ne tenter l'enregistrement que sur une absence confirmée, et afficher les autres erreurs |
| J — installation reprenable | `deploy/Laboutik/install.py` | Ajout le 26 septembre, `a58a15f8` ; conserve les appairages existants et évite certains doublons lors d'une reprise |
| I — configuration Django | `deploy/Laboutik/settings.py` | Booléens SMTP TLS/SSL corrigés, backend email configurable, répertoire de templates des sources ; PostgreSQL est déjà natif |
| K — liens d'interface | `source_templates/login.html`, `kiosk_base.html`, `infos.html`, et le template admin partagé | Liens des sources sur la connexion, le kiosque, les informations et l'administration |

Les anciens fichiers complets portent aussi ces écarts encore présents :

| Écart avec LaBoutik native | Méthode ou fichier concerné |
| --- | --- |
| Méthode de vente de billets absente | `Commande.methode_BI` dans `views.py` |
| Vérification facultative de la validité réelle des adhésions auprès de Lespass absente | `check_carte`, `Commande.methode_VT` dans `views.py` |
| Première carte du responsable choisie au lieu de sa carte primaire | `Commande.methode_AD` dans `views.py` et `NFCCard.badge` dans `fedow_api.py` |
| Traitement des erreurs d'adhésion différent | `Commande.methode_AD` |
| Code HTTP ou erreurs retournés sur échec, au lieu de l'exception native attendue par l'appelant | `Subscription.create_sub` dans `fedow_api.py` |
| Tolérance native d'un 400 d'unicité `first_tag_id` après réinitialisation locale absente ; 201/409 toujours acceptés | `NFCCard.create` |
| Carte introuvable normale, 404, écrite comme erreur dans les logs | `NFCCard.retrieve` |
| Code d'erreur transmis comme entier au lieu d'une chaîne | `Transaction.refill_wallet`, `Transaction.to_place` |

Ce sont les « écarts hérités » : des différences conservées avec une ancienne
copie complète, sans décision individuelle de garder chaque divergence.
Le diff établit ces différences ; il ne prouve pas un incident en production.
Les imports, commentaires et notices de modification diffèrent également.

F et les méthodes réseau `_get`/`_post` ont déjà retrouvé le texte exact de la
référence. Les fichiers restent montés pour E et les autres différences.

## Présentation historique dans les fichiers statiques

Deux copies présentes dans `deploy/Lespass/www/static/reunion/` diffèrent des
sources natives `BaseBillet/static/reunion/`. Elles étaient déjà recensées dans
la liste exhaustive précédente ; leurs effets sont détaillés ici.

| Copie | Différences de contenu |
| --- | --- |
| `css/tibillet.css` | Police DM Serif Text, fond bleu et contrastes, taille du logo ; masque les accès adhésions/agenda et les entrées adhésions/réservations de Mon compte |
| `js/membership-form.mjs` | Supprime des liens d'adhésion et d'agenda ; ajoute « Site du Gala » et « Recharger / Gestion carte » ; change le titre d'accueil ; retire les choix langue/thème ; remplace la marque et le favicon par `logo.webp` ; remplace certains libellés KIN par Gala-am-Aix |

Import dans le fork : `bc5b1a85`, le 21 septembre. Le répertoire `www` est monté
dans Django et Nginx, mais `start.sh` lance aussi `collectstatic --no-input`.
La présence de ces copies dans le dépôt ne prouve donc pas qu'elles sont
actuellement servies telles quelles. Aucun fichier servi n'a été vérifié sur
un serveur dans ce travail. Les chemins de logo et de police sont des références
du code ; leur présence effective n'est pas établie par le diff Git.

## Déploiement et exploitation

Le dépôt initial Lespass comportait déjà son propre déploiement Docker.
Les éléments ci-dessous constituent notre déploiement Gala ajouté sous `deploy/`.

| Ensemble | Différences introduites |
| --- | --- |
| Stacks Compose | Définitions Gala pour Fedow, LaBoutik, Lespass et Traefik ; services PostgreSQL, Redis/Memcached selon l'application ; réseaux, variables de runtime, persistance et montages de code |
| Livraison des images | Compose de release ; images épinglées par manifestes ; build Lespass local remplacé par le digest ECR en release ; résolution des domaines vers l'hôte local |
| L — Nginx | Domaines Gala ; proxy Django et WebSockets ; statiques/médias ; logs ; réglages d'upload et buffers ; routes `/source/` ; alias LaBoutik `/admin` vers `/adminstaff/` et Lespass `/adminstaff` vers `/admin/` |
| Traefik | Entrée publique, routage entre stacks et certificats TLS ; découverte des services Docker |
| Infrastructure AWS | Terraform et bootstrap : EC2 par Gala, région Paris, réseau, IAM, Identity Center/organisation, registre des galas, IP active et intégrations partagées |
| Stockage et secrets | S3 pour livraison/sauvegardes, Secrets Manager, initialisation des identifiants, matérialisation des environnements et accès SSO ; outillage historique Infisical également présent |
| Pipeline | CodeBuild/CodePipeline ; phases Foundation, build/test, Smoke, validation et promotion production ; validations Terraform et manifestes ; bascule du Gala actif |
| Initialisation applicative | Scripts de réconciliation des trois applications, appairages, clés Fedow, tenant/domaine, bouton recharge et webhook Stripe ; outil de configuration du compte admin commun |
| Contrôles de livraison | Préflight, règles des cibles autorisées/interdites, contrôle des releases, vérification du bootstrap, healthchecks et vérification Celery/QR |
| K — publication des sources | Archives originales épinglées et vérifiées, reconstruction des sources correspondant aux fichiers montés, liens `/source/`, publication GitHub et contrôles de disponibilité |
| Sauvegarde et restauration | Scripts PostgreSQL, vérification de restauration isolée, service et timer systemd de sauvegarde |
| Gestion de l'hôte | Démarrage/arrêt des stacks, démarrage systemd, swap, libération d'espace de déploiement ; scripts de démarrage/setup historiques conservés |
| Manifestes | 14 fichiers de release dans `releases/`, catalogues/exemples des versions et images, exemples de registre Gala |

Les quatre Compose actifs déclarent **46 montages distincts par service et
49 déclarations brutes** : trois déclarations Python LaBoutik sont dupliquées.
Les fichiers Compose de release changent les images et la résolution réseau,
pas ces volumes. Ce comptage provient du dépôt, pas d'un Docker de production.

| Type de montage | Nombre de montages par service |
| --- | ---: |
| Code/configuration Python remplacés | 8 |
| Templates remplacés ou ajoutés | 9 |
| Configuration Nginx | 3 |
| Offre de sources | 3 |
| Bases PostgreSQL persistantes | 3 |
| Répertoires www | 7 |
| Journaux | 7 |
| Sauvegardes | 2 |
| Configuration SSH | 2 |
| Socket Docker | 1 |
| Certificats TLS | 1 |

## Construction documentation tests et archives

| Ensemble | Différences |
| --- | --- |
| Dockerfile Lespass | Python 3.11 Debian Bookworm au lieu de Bullseye ; installation APT regroupée et nettoyage des index ; dépendances Poetry inchangées |
| Exclusions Git/Docker | `.gitignore`, `.dockerignore` et exclusions sous `deploy/` ; protection des secrets/état runtime et sorties générées ; trois fichiers `.claude/` versionnés |
| Crédits et notices | `AUTHORS.md`, `NOTICE.md`, `README.md`, notices dans les copies modifiées ; licence principale inchangée |
| Documentation et audits | Guides d'architecture/opérations, politiques de périmètre, inventaires, preuves et dossier `features-enlevees` ; notes/objectifs/consignes `.claude/` |
| Tests | 5 fichiers de tests Lespass ajoutés : parcours QR, E2E QR/Fedow, transport local, domaine Gala, bouton recharge ; 21 fichiers sous `deploy/tests/` ; sondes et vérificateurs de restauration sous `TECH_DOC/` |
| Archives | 20 entrées Git classées comme copies historiques hors des quatre stacks actives : LaBoutik 100J, Lespass V2 et ancien parcours QR ; références de sous-modules `Lespass/app` et `Lespass-v2/app` conservées sous `deploy/` |
| Outils historiques | 12 scripts sous `deploy/tools/scripts/` : images produits, création de bars, emojis, recherche/suppression de cartes, sauvegarde/reset de soldes ; leur présence ne prouve pas leur exécution |

La référence source de l'image LaBoutik comporte aussi l'écart de construction
`docker_push_update.sh`, version `1.4` vers `1.7`, enregistré dans le catalogue
de provenance de l'image. Il est distinct des personnalisations métier Gala.

## Retraits déjà appliqués localement

| Ancien repère | État local |
| --- | --- |
| C — happy hour | Retiré ; prix et validation native restaurés |
| D — limite de terminaux | Retirée, avec exemption admin et logique d'exclusion du plus ancien |
| F — option monnaie cadeau | `ENABLE_GIFT_ASSET_SYNC` retirée ; synchronisation native restaurée |
| G — ancien serializer Fedow | Copie et montage retirés ; protections natives de l'image rétablies |

Le seul montage supprimé à ce stade est G. Les retraits C/D/F concernent des
fonctions dans des fichiers encore montés pour d'autres différences.

## Éléments absents ou inchangés

Les modèles/migrations Lespass, `BaseBillet/views.py`, le template natif de
solde, `pyproject.toml` et `poetry.lock` sont inchangés depuis la base du fork.

Le formulaire 100J de demande de remboursement hors Stripe par IBAN/BIC,
l'affichage du solde total multi-monnaies, l'ancien login existant sans preuve
email, l'endpoint historique `register_nfc_card`, l'outil `card_printer/` et
certains noms de bars du relevé historique ne sont pas portés dans la stack
active. Cette liste décrit des reprises historiques absentes ; elle ne les
présente pas comme des suppressions du TiBillet vanilla de référence.

## Vérification de cet inventaire

Le diff Git actuel a été recompté. Depuis `717021e1`, seules les trois pièces de
l'inventaire précédent ont été ajoutées : aucun code applicatif n'a changé.
Les empreintes des 17 cibles Fedow/LaBoutik correspondent toujours aux sources
déjà auditées. Les deux copies CSS/JS ont été comparées aux sources natives,
leur introduction Git et le mécanisme `collectstatic` ont été relus.

Aucun nouveau test de paiement, vente, remboursement ou charge n'a été lancé.
La liste des fichiers couvre les entrées versionnées ; elle ne prétend pas
recenser le contenu généré ou non versionné des volumes en production.

## Périmètre souhaité après la discussion du 5 octobre

L'utilisateur souhaite un retour au plus près de TiBillet vanilla, avec des
modifications principalement visuelles ou très simples. Les quatre
personnalisations explicitement retenues sont le parcours QR, la présentation
du site, le dashboard financier et l'enregistrement automatique des cartes.
Le QR et l'enregistrement des cartes restent des exceptions fonctionnelles :
ils touchent respectivement aux comptes/liaisons et à l'enrôlement des cartes.

La cible proposée est de reprendre les fichiers natifs exacts et de n'y ajouter
que ces exceptions. Les anciens écarts de billetterie, validité d'adhésion,
sélection de carte et traitement des erreurs ne sont pas nécessaires à ce
périmètre et sont candidats à la restauration exacte. Le dashboard Gala doit
être ajouté séparément des vues/routes natives, et les règles visuelles
existantes doivent être isolées des fichiers JavaScript natifs.

Les adaptations de domaine, visibilité de recharge et email ont des dépendances
identifiées dans le déploiement actuel. Le transport Fedow local dépend des
Galas inactifs partageant les domaines publics. PostgreSQL Fedow et l'installateur
reprenable sont des dépendances de l'état et du workflow actuels ; leur nécessité
ne s'étend pas automatiquement à toute architecture future. Une suppression
doit être précédée d'une solution native vérifiée pour cette dépendance.

L'accès admin demandé précédemment et l'offre de sources existante restent
consignés séparément. La pipeline/infrastructure sera évaluée comme un ensemble
distinct. La demande initiale de remboursement hors Stripe reste ouverte.

Cette section conserve la décision et la proposition de tri. Aucun retrait,
refactoring applicatif, migration de données ou déploiement supplémentaire
n'est effectué pendant cette discussion.

## Compatibilité SQLite et PostgreSQL dans Fedow

La vérification locale du 5 octobre porte sur les 85 fichiers Python de la
source Fedow épinglée et les 3 fichiers Python actuels sous `deploy/Fedow`.
Une analyse syntaxique ne détecte aucun import SQLite, appel direct à un curseur
SQL, `raw`, `extra`, `RawSQL` ou `RunSQL` dans ce périmètre. Les accès examinés
passent par l'ORM Django, qui génère le SQL selon le moteur configuré.
Cela ne garantit pas des comportements identiques entre moteurs.

Un cas concret concerne `Configuration.stripe_api_key` et
`Configuration.stripe_endpoint_secret_enc` : la source native déclare des
champs de 100 caractères, puis y stocke le résultat d'un chiffrement Fernet.
Un essai local avec une valeur fictive de 38 caractères produit 140 caractères
chiffrés, acceptés dans une colonne SQLite `varchar(100)` en mémoire. PostgreSQL
refuse une insertion dépassant la longueur de ce type. Ce risque concerne
l'enregistrement des secrets Stripe, pas une corruption de solde démontrée.
Sources : [types SQLite](https://www.sqlite.org/datatype3.html),
[types texte PostgreSQL](https://www.postgresql.org/docs/15/datatype-character.html).

Le script existant
[`reconcile-fedow-webhook.py`](../../deploy/tools/runtime/reconcile-fedow-webhook.py)
convertit ces deux colonnes PostgreSQL en `text` avant d'enregistrer les secrets.
Cette correction modifie le schéma en dehors des migrations natives Django et
emploie du SQL propre à PostgreSQL. Son exécution et les types réels des colonnes
sur le serveur n'ont pas été vérifiés ici. Les neuf scénarios financiers natifs
déjà conservés dans le dossier G ne testent pas cette sauvegarde des secrets.

L'outil Lespass `import_geoloc_from_sqlite.py` lit explicitement un fichier
SQLite externe de géolocalisation ; ce fichier reste indépendant des bases
applicatives PostgreSQL. Lespass et LaBoutik emploient déjà PostgreSQL dans leurs
références natives. Le changement de moteur à examiner concerne donc Fedow.

## Décision de retour à SQLite pour Fedow

L'utilisateur choisit ensuite de revenir à SQLite et demande de conserver la
configuration PostgreSQL et le code associé. Les 17 fichiers de référence sont
archivés à l'identique depuis le commit comparé, avec les hashes Git et SHA-256,
dans [le dossier I](../features-enlevees/I-postgresql-fedow/README.md).

Le bloc de configuration SQLite natif a été préparé sans réécriture et dix
scénarios ont été vérifiés localement avec les sources Fedow natives et une
base SQLite dédiée. Les résultats et les limites sont consignés dans ce dossier.
Le transfert de données, la sauvegarde SQLite et la bascule restent à qualifier ;
la configuration active du dépôt et les serveurs ne sont pas modifiés par cette
préparation. Lespass et LaBoutik restent sur leur moteur PostgreSQL natif.
