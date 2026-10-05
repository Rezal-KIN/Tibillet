# Inventaire complet des différences avec TiBillet après le retrait du dashboard Gala

Cet inventaire décrit le dépôt local au commit
`e62ddf7194887bd5c4eb2736aa2fd51b134b9577`, vérifié le 5 octobre 2026, avant
la création d'une nouvelle instance. Le retour de Fedow à SQLite est présent.
Le dashboard Gala a également été retiré : les vues et templates natifs de
Fedow reprennent la main. Il reste les trois personnalisations demandées,
plusieurs adaptations techniques et des écarts hérités des anciennes copies
complètes de sources.
Ces derniers ne constituent pas tous des fonctionnalités choisies.

Le travail de cet inventaire ne modifie aucun code applicatif et ne crée ni
ne déploie d'instance. Il ne vérifie pas les données ou le code d'un serveur.
L'[audit initial](2026-10-03-fork/INDEX.md) et les inventaires antérieurs sont
conservés sans modification.

## Références et comptage

| Composant | Référence native utilisée |
| --- | --- |
| Lespass | `TiBillet/Lespass@fd7680891c31bbdf6215e7a0750074de89ff5e8e`, base du fork ; même arbre Git que `f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9` dans l'histoire réécrite |
| Fedow | `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c`, source de l'image épinglée |
| LaBoutik | `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`, source de l'image épinglée |

« TiBillet d'origine » désigne ici ces références fixes. Cet inventaire ne
compare pas le fork aux dernières branches `main` amont. Les références des
images sont dans [`image-sources.json`](../../deploy/source/image-sources.json).
Les archives Fedow et LaBoutik ont été revérifiées par SHA-256 avant lecture.

Le comptage des fichiers est reproductible depuis la racine avec :

```sh
git diff --name-status fd7680891c31bbdf6215e7a0750074de89ff5e8e e62ddf7194887bd5c4eb2736aa2fd51b134b9577
```

Le diff Git du commit comparé comporte **303 chemins différents : 288 ajoutés
et 15 modifiés**. Il comprend les documents, tests, archives et l'infrastructure.
Ce nombre ne représente pas 303 modifications du fonctionnement métier.
Les trois documents du précédent inventaire après SQLite et les trois du
présent inventaire sont hors du commit comparé. Leur conservation ajoute
six chemins documentaires, soit 309 chemins différents une fois ces audits
inclus. Le snapshot applicatif analysé reste celui de `e62ddf71`.

| Catégorie de fichiers | Nombre |
| --- | ---: |
| Application Lespass | 16 |
| Sources actives remplaçant ou complétant les images Fedow et LaBoutik | 10 |
| Déploiement, configuration, tests et documentation sous `deploy/` | 151 |
| Documentation et audits, dont les archives PostgreSQL et dashboard retirés | 72 |
| Construction et exclusions Git/Docker | 3 |
| Copies historiques hors des quatre stacks actives | 20 |
| Outils historiques, dont la présence ne prouve pas l'exécution | 12 |
| Manifestes de release | 14 |
| Tests Lespass ajoutés | 5 |

Annexes : [liste exhaustive des 303 fichiers](2026-10-05-differences-apres-dashboard-fichiers.tsv),
[références, empreintes, fonctions et montages](2026-10-05-differences-apres-dashboard-preuves.json).
Chaque entrée TSV indique le rôle, le mode d’exécution, le hash et les premiers
et derniers commits de changement sur la lignée principale du fork. Ces dates
retracent l’introduction dans notre dépôt ; elles ne prouvent pas la date
d’écriture originale de chaque ancienne copie.
La catégorie générale de déploiement inclut les deux copies CSS/JavaScript
détaillées ci-dessous.

## Les trois personnalisations demandées encore actives

| Personnalisation | Fonction et introduction | Mode d'introduction actuel |
| --- | --- | --- |
| Parcours QR | Inscription ou connexion depuis la carte, preuve email pour un compte existant, liaison carte/portefeuille et retour à la carte ; portage ciblé `6a1d7b87` le 26 septembre | Vues, routes, helper d'authentification et templates dans l'image Lespass |
| Présentation du site et guide rapide | Guide en trois étapes, textes, pages QR et adaptations visuelles ; guide `35786671` le 26 septembre, copies statiques importées par `bc5b1a85` le 21 septembre | Templates dans l'image Lespass ; deux anciennes copies CSS/JS sous `www/static` |
| Enregistrement automatique des cartes | Une absence confirmée déclenche l'enregistrement, puis la relecture ; les autres erreurs restent des erreurs ; correction ciblée `717021e1` le 3 octobre | Deux fonctions personnalisées dans les copies complètes `views.py` et `validators.py` de LaBoutik |

Le QR et l’enregistrement des cartes touchent au fonctionnement des comptes
et des cartes. Les personnalisations CSS/JS anciennes masquent aussi des
menus ; elles ne changent pas seulement les couleurs. Le dashboard Fedow
actuel est celui de l’image native : le suivi Gala et ses six montages ont
été retirés par `e62ddf71`, le 5 octobre. Son index réseau est public selon le
comportement natif ; ses détails monnaie/lieu exigent le statut administrateur.

## Lespass et ses adaptations supplémentaires

Lespass conserve **16 fichiers applicatifs différents : 10 modifiés et
6 ajoutés**. Ils sont intégrés à l'image construite depuis ce dépôt.

| Fichiers | Différence restante |
| --- | --- |
| `BaseBillet/views_qr_card.py`, `BaseBillet/urls.py`, `AuthBillet/utils.py` | Parcours QR ; helper avec indicateur `return_created` et choix du template email |
| `BaseBillet/templates/emails/qr_connexion.html`, `BaseBillet/templates/reunion/views/qr_landing.html`, `qr_check_email.html` | Email et écrans du parcours QR |
| `BaseBillet/templates/reunion/views/home.html` | Guide de connexion rapide et adaptation de l'accueil |
| `BaseBillet/templates/reunion/views/register.html` | Texte de recharge, jeton CSRF et suppression de logs navigateur contenant l'email |
| `BaseBillet/tasks.py` | Liens complets de connexion et URL de retour retirés des logs |
| `Administration/admin/site.py` | Connexion admin Django par mot de passe lorsque `GALA_APEX_TENANT=1` ; sinon redirection vers `/?login=1` au lieu de `/` ; ajout `1d98cb56` le 3 octobre |
| `Administration/management/commands/configure_gala_apex.py` | Association du domaine public au tenant Gala et réglage des liens/emails primaires ; ajout `cb39884d` |
| `Administration/management/commands/configure_gala_refill.py` | Activation du champ natif `force_show_refill_button`, pour afficher le bouton de recharge Fedow/Stripe ; ajout `a9b2ff7f` |
| `fedow_connect/fedow_api.py` | Sous `GALA_LOCAL_FEDOW=1`, transport HTTP sur le réseau Docker vers `fedow_nginx`, en conservant le Host public et les signatures ; sinon transport HTTPS natif ; ajout `ed5cb0c6` |
| `TiBillet/settings.py` | Variables SMTP TLS/SSL interprétées en booléens, backend email configurable |
| `Administration/admin/dashboard.py`, `seo/templates/seo/partials/tibillet_community_links.html` | Liens de publication des sources dans l'administration et le footer public |

Le transport local et la résolution locale des domaines permettent à un Gala
inactif d'initialiser ses propres services alors que les domaines publics
pointent vers le Gala actif. Leur nécessité dépend donc du déploiement retenu.
Les délais réseau natifs de Lespass sont conservés.

L'outil `deploy/tools/runtime/configure-gala-admin.py` configure le compte
commun sur les trois applications. Il reçoit le mot de passe par saisie
ou une empreinte Django via stdin ; le mot de passe demandé n'est pas stocké
en clair dans le dépôt. Cet outil n'est pas lancé automatiquement par une
livraison générique : sa présence ne garantit pas les identifiants d'une
nouvelle instance. Aucun compte distant n'a été contrôlé par cet inventaire.

## Les anciennes copies de présentation

| Copie locale | Différence avec le fichier statique natif |
| --- | --- |
| `deploy/Lespass/www/static/reunion/css/tibillet.css` | Police DM Serif, fonds bleus, contrastes et taille de logo ; masquage des adhésions, de l'agenda et de certaines entrées du compte |
| `deploy/Lespass/www/static/reunion/js/membership-form.mjs` | Menus Gala/recharge-carte, modification de l'entête, masquage d'autres liens et des choix de langue/thème, branding KIN/Gala et références au logo/favicon |

Les fichiers sources correspondants sous `BaseBillet/static/` sont inchangés
depuis le fork. Ces copies sont dans le répertoire `www` monté, tandis que
`collectstatic --no-input` est exécuté au démarrage natif. Elles peuvent donc
être remplacées lors de cette collecte. Leur présence dans Git ne prouve pas
qu'elles seront effectivement servies après une installation neuve. Le rendu
et les assets référencés restent à vérifier sur cette installation.

## Fedow

Fedow conserve **2 cibles source personnalisées** : un fichier Python de
réglages complet et le template admin partagé avec LaBoutik. Le bloc
`DATABASES` est **identique au texte SQLite de la référence native**.

| Source locale | Différence restante |
| --- | --- |
| `deploy/Fedow/settings.py` | Hôtes et origines CSRF de sous-domaine ajoutés seulement en DEBUG au lieu de toujours ; browser reload activé en DEBUG au lieu d’être désactivé ; répertoire `source_templates` ajouté ; notice de modification |
| `deploy/source/admin-templates/admin/base_site.html` | Template admin partagé, ajout du lien vers les sources |

Les anciens remplacements de `fedow_dashboard/views.py`, `urls.py` et de
quatre templates ont disparu. Les analyses natives du réseau et des monnaies,
leurs caches, leurs graphiques et les décorateurs `@staff_member_required`
de `asset_view` et `place_view` sont donc sélectionnés directement depuis
l’image. Les routes `/dashboard/suivi/` et `/dashboard/suivi/data/` n’existent
plus dans cette sélection. L’accueil réseau natif reste public ; le retour
au standard ne réserve pas tout Fedow aux administrateurs.

Les six sources retirées sont archivées à l’identique dans le
[dossier H](../features-enlevees/H-dashboard-financier/README.md). Le lien
vers les sources dans l’admin, `/source/` et l’en-tête HTTP `Link` sont
conservés. Les liens ajoutés au footer du dashboard et à l’accueil public
ont disparu avec les templates personnalisés.

Le dashboard et les serializers de transactions sont maintenant fournis par
l’image native épinglée. Le fichier `settings.py` reste toutefois un
remplacement complet par volume : Fedow n’est donc pas entièrement sans
surcharge de code. La comparaison ne constitue pas une validation financière
sur une instance réelle.

## LaBoutik

LaBoutik conserve **9 cibles source personnalisées**, dont le template admin
partagé avec Fedow. Chaque fichier Python monté remplace le fichier complet
de l'image, y compris ses parties sans rapport avec la personnalisation utile.

| Sources locales sous `deploy/Laboutik/`, sauf indication contraire | Différence choisie ou technique |
| --- | --- |
| `views.py`, `validators.py` | Enregistrement automatique des cartes inconnues ; correction minimale limitée à une absence confirmée, suivie d'une relecture |
| `install.py` | Installateur reprenable : conserve les appairages existants et évite certains doublons lors d'une reprise ; ajout `a58a15f8`, conservé pour l'instant |
| `settings.py` | Réglages SMTP TLS/SSL, backend email configurable, répertoire des templates de sources ; PostgreSQL reste le moteur natif |
| `fedow_api.py` | Ancienne copie de communication avec Fedow ; délais GET/POST natifs restaurés, autres divergences ci-dessous encore présentes |
| `source_templates/login.html`, `kiosk_base.html`, `infos.html` | Liens vers les sources dans la connexion, le kiosque et les informations |
| `deploy/source/admin-templates/admin/base_site.html` | Lien vers les sources dans l'administration |

Les **écarts hérités** désignent les différences laissées par ces anciennes
copies complètes, sans décision de conserver chaque comportement séparément.
Ce n'est pas une justification pour les garder.

| Écart encore présent | Conséquence ou limite établie par les sources |
| --- | --- |
| `Commande.methode_BI` absent de `views.py` | Le traitement natif de vente de billets correspondant n'est plus disponible dans la copie |
| Vérification facultative de la validité réelle des adhésions Lespass absente de `check_carte` et `Commande.methode_VT` | Ancienne logique fondée sur la présence d'un token d'adhésion, sans reprendre ce contrôle natif de validité |
| Sélection de carte différente dans `Commande.methode_AD` et `NFCCard.badge` | Première carte du responsable utilisée au lieu de la carte primaire recherchée par le code natif |
| Erreurs d'adhésion différentes dans `Commande.methode_AD` et `Subscription.create_sub` | Retour d'un code HTTP entier ou d'un dictionnaire d'erreurs là où le code natif lève une exception ; possibilité d'une erreur ultérieure chez l'appelant |
| Tolérance native de certains doublons absente de `NFCCard.create` | Les réponses 201/409 sont admises, mais le cas natif 400 d'unicité `first_tag_id` après réinitialisation locale peut bloquer |
| Carte inconnue 404 écrite comme erreur dans `NFCCard.retrieve` | Bruit de logs au lieu du traitement natif d'une absence normale |
| Type des codes d'erreur différent dans `Transaction.refill_wallet` et `Transaction.to_place` | Entier transmis au lieu de la chaîne utilisée par la référence |

Les imports, commentaires et notices diffèrent aussi. Les détails et les
empreintes de chaque source figurent dans l'annexe JSON. Le diff établit des
divergences ; il ne démontre pas un incident financier. Les timeouts natifs
`(3, 5)` de GET/POST ont déjà été restaurés et ne font plus partie de ces écarts.

## Montages restant dans les quatre stacks actives

Les Compose Fedow, LaBoutik, Lespass et Traefik déclarent **40 montages distincts
par service, 43 déclarations brutes**. Trois lignes Python LaBoutik sont
dupliquées. Les Compose de release n'ajoutent aucun volume. Certains montages
de données existent aussi dans le déploiement Docker natif : les 40 ne sont
pas tous des modifications métier.

| Type de montage | Nombre |
| --- | ---: |
| Code/configuration Python remplacés | 6 |
| Templates remplacés ou ajoutés, dont le répertoire admin partagé compté dans les deux services | 5 |
| Configuration Nginx | 3 |
| Publication des sources | 3 |
| Bases persistantes : Fedow SQLite, Lespass PostgreSQL, LaBoutik PostgreSQL | 3 |
| Répertoires www de statiques, médias et autres fichiers applicatifs | 7 |
| Journaux | 7 |
| Sauvegardes | 2 |
| Configuration SSH | 2 |
| Socket Docker | 1 |
| Certificats TLS | 1 |

Les **6 remplacements Python** sont précisément :

| Composant | Sources locales |
| --- | --- |
| Fedow, 1 | `deploy/Fedow/settings.py` |
| LaBoutik, 5 | `deploy/Laboutik/settings.py`, `install.py`, `views.py`, `fedow_api.py`, `validators.py` |

Lespass ne remplace pas son Python par ces montages : ses modifications sont
dans l'image. Les données SQLite de Fedow sont montées depuis
`deploy/Fedow/sqlite-database`, séparément de l'ancien répertoire PostgreSQL
`deploy/Fedow/database`. Aucun effacement ou transfert de données n'a été
effectué par cet inventaire. Il décrit la conservation séparée prévue par
le rollback ; il ne vérifie pas le contenu d’un disque distant. La liste des
sources, destinations, modes et commits d’introduction est dans l’annexe JSON
et reproduite en fin de document.

## Déploiement et exploitation ajoutés au fork

Ces éléments restent des différences avec le dépôt Lespass initial, même
lorsqu'ils ne changent pas directement les règles de caisse.

| Ensemble | Différences restantes |
| --- | --- |
| Stacks Compose Gala | Quatre stacks, variables runtime, réseaux, appairages locaux, persistance, redémarrages et montages ; PostgreSQL Lespass `13-bookworm`, PostgreSQL LaBoutik `11.5-alpine`, Fedow SQLite, caches selon les applications ; les trois moteurs sont les moteurs natifs |
| Livraison d'images | Digests épinglés, Compose de release, image Lespass livrée via ECR et résolution des domaines vers l'hôte local |
| Nginx | Domaines Gala, proxy Django/WebSockets, statiques/médias, logs, réglages de buffers/upload et `/source/` ; alias LaBoutik `/admin` vers `/adminstaff/`, Lespass `/adminstaff` vers `/admin/` ; décision de retrait reportée |
| Traefik | Routage public, découverte Docker et certificats TLS |
| Infrastructure AWS | Terraform et bootstrap : EC2 par Gala, région Paris, réseau, IAM, Identity Center/organisation, registre des galas, IP du Gala actif et intégrations partagées |
| Stockage et secrets | Livraison et sauvegardes S3, Secrets Manager, génération d'identifiants, matérialisation des environnements et accès SSO ; anciens outils Infisical également conservés |
| Pipeline | Neuf fichiers buildspec CodeBuild/CodePipeline : Foundation plan/apply/finalize, test/build, déploiement Smoke, production validate/promote et Gala actif plan/apply ; contrôles Terraform/manifeste, validations humaines et bascule du Gala actif |
| Initialisation applicative | Réconciliation des trois applications, clés/appairages Fedow, tenant/domaine, visibilité recharge, configuration Stripe/webhook et outil du compte admin commun |
| Contrôles de livraison | Préflight, politiques de périmètre/cibles, validation des releases et du bootstrap, healthchecks, Celery et vérification QR |
| Publication des sources | Archives amont épinglées, reconstruction selon les fichiers montés, checksums, liens publics `/source/`, publication GitHub et contrôles de disponibilité ; conservée |
| Sauvegarde/restauration | Sauvegarde cohérente SQLite par API Python, dumps PostgreSQL des deux autres applications, vérification isolée de restauration, compatibilité des anciennes sauvegardes Fedow PostgreSQL et timer systemd |
| Préparation de Fedow vide | Outil `fedow-sqlite.py` et marqueur de préparation explicite, contrôlé avant démarrage ; évite de traiter silencieusement un dossier vide comme une base existante |
| Gestion de l'hôte | Démarrage/arrêt des stacks, service systemd, swap, récupération d'espace et anciens scripts de setup/démarrage |
| Manifestes | 14 fichiers de release dans `releases/`, catalogues et exemples de versions/images/registre Gala |

La publication des sources comprend des liens et pages statiques, mais aussi
une dépendance de déploiement : une source manquante ou incohérente peut bloquer
une livraison. Aucun contrôle GitHub périodique n'arrête l'instance en service.

Le schéma des secrets générés conserve encore le champ historique
`fedow_postgres_password` et des variables PostgreSQL Fedow inutilisées par
le nouveau backend. Ce sont des reliquats de configuration, pas une base
PostgreSQL Fedow encore active dans les Compose actuels.

## Construction documentation tests et archives

| Ensemble | Différences restantes |
| --- | --- |
| Dockerfile Lespass | Python 3.11 sur Debian Bookworm au lieu de Bullseye ; installation APT regroupée et nettoyage des index ; dépendances Poetry inchangées |
| Exclusions | `.gitignore`, `.dockerignore` et exclusions sous `deploy/`, dont secrets, état runtime, données SQLite et sorties générées |
| Attribution | `AUTHORS.md`, `NOTICE.md`, `README.md` et notices de modification dans les copies ; licence principale inchangée |
| Documentation | Guides d'architecture/exploitation, périmètres, audits, preuves, dossier `features-enlevees` et trois fichiers `.claude/` |
| Tests | 5 fichiers Lespass ajoutés : QR, E2E QR/Fedow, transport local, domaine et bouton recharge ; 22 fichiers de tests sous `deploy/tests/` ; sondes/vérificateurs sous `TECH_DOC/` |
| Archives anciennes | 20 entrées Git hors de la chaîne de release : ancienne LaBoutik 100J, Lespass V2 et ancien QR ; elles peuvent être consultées ou lancées manuellement selon le fichier |
| Sous-modules | `deploy/Lespass/app` : `3a4dedb47d4a116dec45617b10c7a01cb2d902c1`, contexte de build local/dev ; `deploy/Lespass-v2/app` : `bc681a34fb1d08c3ba3fdd715d529742b797388e`, ancienne stack V2 hors release |
| Archives des retraits | Configuration PostgreSQL depuis `4c6091eb` et dashboard depuis `7f31acd3`, à l’identique avec manifestes Git/SHA-256 ; aucune base ni secret réel dans ces archives |
| Outils historiques | 12 scripts sous `deploy/tools/scripts/` : images produits, bars, emojis, recherche/suppression de cartes, sauvegarde/reset des soldes ; présence distincte de leur exécution |

Les trois fichiers `.claude/` sont des instructions, notes et objectifs
pour les agents ; certains objectifs V2 sont historiques. Ils ne sont pas
chargés par Django. Les archives sous `TECH_DOC/` et les tests ne s’exécutent
pas spontanément dans les applications.

Les douze scripts de maintenance historiques peuvent modifier des données
s’ils sont lancés manuellement, notamment les suppressions de cartes et le
reset de soldes. Aucun appel à ces scripts n’a été trouvé dans la chaîne de
release actuelle hors références des tests/politiques. `reset_soldes.sh` écrit
encore `suivi_session_start.txt`, devenu inutilisé par le dashboard natif.
Ces fichiers exécutables ne sont pas de simples documents sans effet possible.

Le catalogue de provenance LaBoutik documente aussi `docker_push_update.sh`,
version `1.4` remplacée par `1.7`, comme différence de construction de l'image
épinglée. Ce point est distinct des montages et des fonctionnalités Gala.

Le Compose Lespass sans surcharge de release référence encore `./app` comme
contexte de construction. La surcharge de release annule ce build et impose
l'image épinglée ; la référence de sous-module n'est donc pas une surcharge
du Python de cette image livrée.

## Ce qui a déjà été retiré ou reste inchangé

| Personnalisation retirée localement | État actuel |
| --- | --- |
| Happy hour et substitution des prix | Retour aux unités natives de prix et de validation |
| Limite de deux terminaux, FIFO et exemption admin | Retirée |
| Option `ENABLE_GIFT_ASSET_SYNC` | Retirée ; synchronisation native de la monnaie cadeau rétablie |
| Réparations automatiques et ancienne copie du serializer Fedow | Copie et montage retirés ; code natif de l'image, dont ses protections de transaction/concurrence, sélectionné |
| Dashboard financier Gala | Six sources et six montages retirés ; vues/routes/templates natifs sélectionnés directement depuis l’image ; archive H conservée |
| PostgreSQL à la place de SQLite dans Fedow | Bloc SQLite natif restauré, service PostgreSQL Fedow retiré ; ancienne configuration archivée, ancien dossier de données conservé séparément |
| Élargissement SQL des secrets Stripe Fedow hors migrations | `ALTER TABLE` PostgreSQL retiré ; utilisation des accesseurs natifs |

Les retraits sont documentés dans
[`features-enlevees`](../features-enlevees/README.md). Ils n'ont pas été déployés
par cet inventaire. Ils ne rendent pas entièrement natifs les fichiers
LaBoutik ou Fedow qui restent montés pour d'autres différences.

Les modèles et migrations Lespass, `BaseBillet/views.py`, le template natif
de solde, `pyproject.toml` et `poetry.lock` sont inchangés depuis le fork.

Le formulaire 100J de demande de remboursement hors Stripe par IBAN/BIC,
l'affichage du solde total multi-monnaies, l'ancien login existant sans preuve
email, l'endpoint historique `register_nfc_card` et l'outil `card_printer/`
ne sont pas portés dans les quatre stacks actives. Ce sont des ajouts
historiques absents, pas des fonctionnalités vanilla supprimées par ce lot.
Le remboursement natif en ligne de Lespass sélectionne l'actif Stripe ;
le parcours de demande pour un solde local reste un sujet distinct et ouvert.

## Vérification, limites et suite proposée

La liste Git de 303 chemins, les 40 montages et les empreintes des 11 cibles
source Fedow/LaBoutik ont été recalculés. Ces cibles représentent 10 fichiers
locaux, car le template admin est partagé. Les 11 cibles restantes sont
identiques à celles du précédent inventaire SQLite : le retrait H change la
sélection des sources, sans réécrire les autres fichiers montés.

Les trois blocs `DATABASES` ont été comparés textuellement aux références
natives : les trois sont identiques. Les sources statiques Lespass, modèles,
migrations, dépendances Poetry et licence mentionnés plus haut sont inchangés.
Les archives upstream et les archives H/I ont leurs SHA-256 vérifiés. Les
40 fichiers de l’audit initial ont été revérifiés avec leur manifeste ; ils
sont intacts. Les trois documents du précédent inventaire SQLite sont aussi
conservés à l’identique, avec leurs empreintes dans l’annexe JSON.

Le vérificateur existant des retraits passe. Le retrait H avait déjà été
vérifié localement : 54 sources du dashboard identiques dans la reconstruction,
9 tests de publication des sources et 11 requêtes Django avec données fictives
et SQLite en mémoire, sans SQL d’écriture ni changement des soldes. Les reçus
correspondants restent dans le dossier H. Cet inventaire documentaire ne
relance pas des tests de vente, de paiement, de remboursement ou de charge.

Les différences de fonctions de l’annexe JSON incluent leur texte,
décorateurs, commentaires et formatage ; elles ne sont pas toutes des
changements de comportement. Les fichiers ignorés, secrets, données des
volumes, assets générés et état des serveurs ne sont pas recensés. Un inventaire
du dépôt ne garantit ni le fonctionnement réel du gala, ni l’absence
d’incident financier, ni la conformité juridique des remboursements.

Avant une nouvelle instance, les sujets encore ouverts, par priorité, sont :

1. Restaurer **exactement les unités natives LaBoutik** de billetterie,
   adhésions, carte primaire et erreurs, en gardant l’enregistrement automatique
   demandé. Les cinq copies Python complètes sont le principal obstacle restant
   à un fonctionnement maîtrisé proche de TiBillet.
2. Rendre les personnalisations visuelles reproductibles après `collectstatic`
   et examiner si les réglages Fedow nécessitent encore un fichier complet monté.
3. Vérifier le parcours complet QR, email, recharge, caisse et remboursement
   sur la future instance. Le besoin de remboursement hors Stripe demeure
   distinct, sans formulaire 100J actif aujourd’hui.
4. Revoir ensuite les configurations/outils de déploiement devenus inutiles,
   sans confondre les montages de données nécessaires avec les remplacements
   de sources applicatives.

Ces étapes sont proposées pour la suite. Aucun rollback supplémentaire,
changement applicatif, push, déploiement, création d’instance ou modification
de base n’est effectué dans ce travail d’inventaire.

## Liste complète des 40 montages

| Compose / service | Source hôte → destination conteneur | Type | Mode | Introduction dans le fork |
| --- | --- | --- | --- | --- |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./sqlite-database` → `/home/fedow/Fedow/database` | base persistante | rw | `7f31acd3` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./www` → `/home/fedow/Fedow/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./logs` → `/home/fedow/Fedow/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./settings.py` → `/home/fedow/Fedow/fedowallet_django/settings.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `../source/admin-templates` → `/home/fedow/Fedow/source_templates` | template remplace | ro | `01ca8349` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./www` → `/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./logs` → `/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./nginx` → `/etc/nginx/conf.d` | configuration Nginx | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `../source/public` → `/source` | offre sources AGPL | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_postgres` | `./database/data` → `/var/lib/postgresql/data` | base persistante | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./backup` → `/Backup` | sauvegardes | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./ssh` → `/home/tibillet/.ssh` | configuration SSH | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./settings.py` → `/DjangoFiles/Cashless/settings.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./install.py` → `/DjangoFiles/administration/management/commands/install.py` | code/configuration Python remplace | ro | `a58a15f8` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./source_templates/login.html` → `/DjangoFiles/webview/templates/login.html` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./source_templates/kiosk_base.html` → `/DjangoFiles/htmxview/templates/kiosk/base.html` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./source_templates/infos.html` → `/DjangoFiles/htmxview/templates/appsettings/infos.html` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `../source/admin-templates` → `/DjangoFiles/source_templates` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./views.py` → `/DjangoFiles/webview/views.py` (déclaré deux fois) | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./fedow_api.py` → `/DjangoFiles/fedow_connect/fedow_api.py` (déclaré deux fois) | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./validators.py` → `/DjangoFiles/webview/validators.py` (déclaré deux fois) | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./nginx` → `/etc/nginx/conf.d` | configuration Nginx | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `../source/public` → `/source` | offre sources AGPL | ro | `01ca8349` |
| `deploy/Lespass/docker-compose.yml` / `lespass_postgres` | `./database` → `/var/lib/postgresql/data` | base persistante | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./backup` → `/Backup` | sauvegardes | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./ssh` → `/home/tibillet/.ssh` | configuration SSH | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_celery` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `e2ad1406` |
| `deploy/Lespass/docker-compose.yml` / `lespass_celery` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `e2ad1406` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `../source/public` → `/source` | offre sources AGPL | ro | `01ca8349` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./www` → `/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./logs` → `/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./nginx` → `/etc/nginx/conf.d` | configuration Nginx | rw | `bc5b1a85` |
| `deploy/traefik/docker-compose.yml` / `traefik` | `/var/run/docker.sock` → `/var/run/docker.sock` | socket Docker | ro | `bc5b1a85` |
| `deploy/traefik/docker-compose.yml` / `traefik` | `./acme.json` → `/acme.json` | certificats TLS | rw | `bc5b1a85` |
