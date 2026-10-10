# Différences avec TiBillet d’origine — audit du 9 octobre 2026

L’installation conserve des adaptations applicatives choisies pour le Gala, et une couche de livraison/exploitation AWS propre au projet. Les remplacements de Python et HTML par des montages ont été retirés de la chaîne actuelle et leur absence est confirmée sur **Smoke, l’instance active**. L’ancienne instance Aix reste sur une dernière release livrée antérieure aux retraits ; son intérieur est inaccessible pour ce contrôle. **Des montages de données et de configuration subsistent.** Les adaptations Fedow/LaBoutik sont désormais copiées dans les images : cela change leur emballage, pas leur caractère personnalisé.

Cet audit ne déploie rien et ne modifie aucun comportement. Il conserve les audits antérieurs et distingue le code actuel, les données de configuration, le code exécuté seulement pendant une livraison, et les archives.

## Référence et niveau de preuve

Snapshot audité : `Rezal-KIN/Tibillet@cd677bb39cf7efcd43f55cd943d6177fb07cf1ba`, branche `Vaporik/vaporik/remboursements-admin`. `origin/main` pointe localement sur ce même commit ; **ce n’est pas la référence vanilla**.

| Composant | Référence TiBillet utilisée | Forme actuelle |
| --- | --- | --- |
| Lespass | `TiBillet/Lespass@fd7680891c31bbdf6215e7a0750074de89ff5e8e` ; arbre identique à `f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9` dans notre historique réécrit | Image construite depuis le fork |
| Fedow | `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c` ; image native `sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83` | Image dérivée de cette image exacte |
| LaBoutik | `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490` ; image native `sha256:012f3f1a14b532766f6faa9b6dc55ce53b0f2e65de7035066b96e86b30c006e9` | Image dérivée de cette image exacte |

Les archives natives Fedow/LaBoutik sont contrôlées par SHA-256 selon [image-sources.json](../../deploy/source/image-sources.json). Comparaison à ces versions fixes, **pas au dernier `main` de TiBillet**. Ce choix permet de comparer au code correspondant aux références déjà adoptées, sans changer de version pendant l’audit.

Les preuves sont de trois niveaux :

- **Aujourd’hui, dépôt** : comparaison de tous les fichiers versionnés, Dockerfiles, Compose, scripts et blocs de bases de données ; vérification exacte des restaurations natives.
- **Aujourd’hui, HTTP public** : `/source/` répond sur les trois domaines et annonce la release Smoke du commit `cd677bb3`. Le CSS et le JS servis sur le domaine principal sont identiques aux sources personnalisées actuelles.
- **Aujourd’hui, AWS après reconnexion** : compte/région vérifiés, métadonnées des cinq EC2, marqueur/EIP, dernières pipelines, stocks S3 et inspection SSM de Smoke. Sources/images/montages de Smoke contrôlés directement. Les trois autres Galas arrêtés restent arrêtés ; Aix est allumée mais SSM est déconnecté. Leurs contenus internes ne sont pas présentés comme réinspectés. Les reçus du 8 octobre restent la preuve du premier démarrage du Gala neuf.

Un fichier présent dans Git n’est pas nécessairement chargé. Une réponse HTTP ou un diff ne démontre ni l’ensemble du fonctionnement financier, ni une conformité juridique.

## Inventaire chiffré

**348 chemins diffèrent de la référence Lespass d’origine : 331 ajoutés, 17 modifiés, aucun supprimé dans le diff final.** Les retraits de nos propres personnalisations apparaissent dans leur histoire ; ils n’apparaissent pas comme suppressions d’un fichier vanilla lorsque ce fichier avait été ajouté après le fork.

Le [TSV exhaustif](2026-10-09-differences-vanilla-fichiers.tsv) donne, pour chaque chemin, son rôle, sa forme, son utilisation, son empreinte, son premier et dernier changement sur la lignée principale. Cette date d’introduction dans le fork ne prétend pas être la date de création originale dans les 100J.

| Ensemble | Nombre de chemins | Effet/utilisation |
| --- | ---: | --- |
| Application Lespass | 20 | Code, templates et assets dans l’image |
| Sources intégrées aux images Fedow/LaBoutik | 9 | 10 destinations `COPY`, car le template admin commun est utilisé deux fois |
| Construction/exclusions Git et Docker | 3 | Construction/publication ; pas du métier cashless |
| Assemblage Docker courant | 13 | Dockerfiles, Compose de base/release et Nginx |
| Exploitation AWS | 47 | Build, import, initialisation, contrôles, sauvegardes et commandes opérateur |
| Infrastructure AWS | 29 | Terraform et bootstrap ; exemples comptés séparément |
| Étapes de pipeline | 9 | CodeBuild/CodePipeline |
| Configuration et politiques | 6 | Catalogue, références d’images, exclusions et périmètre d’exploitation |
| Contrats de publication/provenance | 3 | Inclut la recette des exceptions NFC lue par le garde de build |
| Tests et garde de restauration native | 34 | Exécutés pendant validation/construction, pas par les pages cashless |
| Documentation/preuves/provenance | 91 | Inclut des sondes d’audit exécutables manuellement ; hors applications |
| Archives de fonctionnalités/anciennes stacks | 40 | Hors chaîne de livraison courante |
| Outils historiques | 15 | Commandes manuelles anciennes, pas lancées par la pipeline actuelle |
| Manifestes de releases historiques | 17 | Sélectionnés seulement pour une livraison précise |
| Exemples de configuration | 9 | Aucun effet tant qu’ils ne sont pas sélectionnés/copiés |
| Sous-module de développement | 1 | Contexte local alternatif, désactivé en release |
| Anciennes copies de statiques | 2 | Doublons exacts des sources désormais intégrées à Lespass |

Ce total décrit le dépôt avant ajout du présent audit et de ses annexes. Les secrets, bases, CSV privés, médias et autres fichiers ignorés sont hors diff Git ; leur rôle est recensé séparément.

## Adaptations applicatives conservées

Dans les tableaux applicatifs, « utilisée » concerne la release courante de **Smoke** et la chaîne actuelle : sélectionnée/chargée par cette release, avec exécution lorsqu’on emprunte le parcours concerné. Cela ne signifie pas qu’un paiement réel ou chaque branche d’erreur a été testé aujourd’hui.

| Différence | But et effet | Forme / fichiers | Utilisation |
| --- | --- | --- | --- |
| Parcours QR Gala | Scanner `/qr/<uuid>/`, inscrire ou retrouver le titulaire, lier la carte, accéder à la recharge/au compte. Compte existant ou carte déjà liée : preuve email et contrôle du titulaire ; compte nouveau : entrée immédiate avec email restant à confirmer | Nouveau `BaseBillet/views_qr_card.py`, trois routes dans `BaseBillet/urls.py`, deux pages QR, email `qr_connexion.html` | Active ; dérivé du besoin 100J, adapté au modèle/API actuels |
| Extension de création/connexion utilisateur | Retour facultatif `(user, created)` et sélection du template email pour le QR ; limite les envois répétés par cache de cinq minutes dans la vue QR | `AuthBillet/utils.py` et vue QR | Active dans le parcours QR ; paramètres existants conservés pour les autres appelants |
| Formulaire de liaison | Texte expliquant la recharge, token CSRF explicite, retrait des emails de la console navigateur | `templates/reunion/views/register.html` | Active |
| Guide cashless d’accueil | Explique récupération de carte, recharge et paiement NFC. Le bouton adhésion hors connexion ouvre le panneau login dans le template | `templates/reunion/views/home.html` | Active ; le CSS/JS peut ensuite masquer l’entrée adhésion |
| Identité visuelle Gala | Fond bleu, typographie DM Serif Text, logo/favicon, contraste compte/tableaux, liens vers `galas-am-aix.com`, intitulés gestion de carte et remplacement de certains libellés KIN | CSS, `membership-form.mjs`, logo WebP, police TTF et licence OFL dans `BaseBillet/static/reunion/` | **Fichiers servis vérifiés aujourd’hui** ; modules chargés par les templates de base |
| Simplification des menus | Masque/supprime agenda, adhésions, réservations du compte, choix langue/thème. Ajoute accès « Recharger / Gestion carte » | Même CSS/JS ; sélecteurs CSS et manipulation du DOM après chargement/HTMX | Active côté interface. **Ce n’est pas seulement cosmétique** ; routes et fonctions serveur restent natives |
| Login admin Lespass par mot de passe | Affiche le formulaire Django quand `GALA_APEX_TENANT=1`. Hors Gala, la redirection native est aussi passée de `/` à `/?login=1` | `Administration/admin/site.py` | Mode Gala activé par configuration runtime ; modification réelle de l’entrée d’administration |
| Domaine principal du Gala | Affecte le domaine racine au tenant événement ; évite d’envoyer QR/emails vers le tenant public générique | Nouvelle commande `configure_gala_apex.py`, utilisant les modèles natifs `Client`/`Domain` | À chaque déploiement ; vérification au healthcheck |
| Bouton de recharge | Active le champ natif `force_show_refill_button` quand les clés Stripe sont cohérentes ; refuse de contourner un masquage explicite | Nouvelle commande `configure_gala_refill.py` ; aucune modification du modèle ni du paiement | À chaque déploiement, puis rendu natif/QR |
| Communication Lespass → Fedow locale | Utilise `http://fedow_nginx` lorsque `GALA_LOCAL_FEDOW=1`, conserve le Host public, les signatures et les délais natifs. Un Gala inactif parle à son propre Fedow | `fedow_connect/fedow_api.py` | Active sur nos Galas ; autre mode : HTTPS public natif |
| Réglages email Lespass | Convertit les chaînes TLS/SSL en booléens ; permet un backend email configurable | `TiBillet/settings.py` | Active ; SMTP Gala, backend sans envoi pour Smoke |
| Réduction des logs sensibles | Retire le lien magique complet et l’URL de retour des logs | `BaseBillet/tasks.py` | Active pour les emails de connexion |
| Liens vers les sources Lespass | Ajoute `/source/` dans l’admin et les liens communautaires | `Administration/admin/dashboard.py`, partial SEO | Active ; ce fichier admin n’est pas notre ancien dashboard financier Fedow |
| Carte NFC inconnue sans QR physique | Sur absence Fedow confirmée (`FileNotFoundError`), crée/retrouve la carte localement, crée via le client Fedow natif, puis exige une relecture. Ne crée pas une carte sur simple erreur réseau | Deux fonctions : `check_carte` dans `deploy/Laboutik/views.py`, `validate_tag_id` dans `validators.py` | Active dans l’image LaBoutik ; les deux chemins ont été exercés contre les services réels le 8 octobre |
| Installation LaBoutik reprenable | Reprend les appairages Lespass/Fedow déjà réussis ; refuse de les déplacer silencieusement ; réutilise l’admin et ne renvoie l’invitation que lors de sa création | `deploy/Laboutik/install.py`, modification de `Command.handle` | Installation/déploiement seulement |
| Réglages email LaBoutik | Même conversion TLS/SSL et sélection du backend ; ajoute le chemin de templates de sources | `deploy/Laboutik/settings.py` | Active |
| Lien sources dans les interfaces LaBoutik | Ajoute lien sources aux pages connexion, kiosque et informations | Trois templates dans `deploy/Laboutik/source_templates/` | Active lorsque ces pages sont utilisées |
| Lien sources dans les admins Fedow/LaBoutik | Template admin héritant du template standard ; seul écart fonctionnel dans les settings Fedow : chemin de ce template | `deploy/source/admin-templates/admin/base_site.html` et `deploy/Fedow/settings.py` | Active ; **aucun changement restant du bloc SQLite, du serializer ou du dashboard Fedow** |

Les diffs Python/HTML Fedow/LaBoutik sont reconstruits depuis les archives natives vérifiées. Les seules fonctions métier modifiées dans ces copies sont les deux fonctions d’enregistrement NFC ; l’installateur constitue une troisième fonction modifiée liée au démarrage. Les notices et chemins/templates/email sont explicitement séparés. Le client `fedow_connect/fedow_api.py` **de LaBoutik** est natif ; ne pas le confondre avec celui de **Lespass**, qui conserve le transport local décrit ci-dessus.

## Images : ce qui diffère et ce qui reste entier

| Image/construction | Différence | Usage |
| --- | --- | --- |
| Lespass | Build du fork. Base système passée de `python:3.11-bullseye` à `python:3.11-bookworm` ; installations APT regroupées, cache APT retiré. `pyproject.toml`/`poetry.lock` inchangés | Construction pipeline Test ; digest ECR dans le manifeste |
| Fedow | Dockerfile depuis digest natif, copie complète de `settings.py` et du template admin ; labels de commit/base et compilation syntaxique | 2 destinations de copie |
| LaBoutik | Dockerfile depuis digest natif, copie complète de quatre Python et quatre HTML ; labels et compilation | 8 destinations de copie |
| Livraison des images | Build/push des trois images, manifestes à digests, contrôle des labels avant démarrage et promotion des images exactement testées | Notre couche AWS, pas du code financier TiBillet |
| Source-offer/build | Garde refusant un écart hors exceptions déclarées et publication du code correspondant | Pendant build/livraison |
| Compose de développement | Des tags peuvent rester flottants (`nginx`, Redis/PostgreSQL, etc.) et des builds locaux sont possibles. Les superpositions release fixent les trois images applicatives et Traefik | La pipeline sélectionne les superpositions release ; ne pas suivre une commande locale de build comme équivalente à une release |

**Nous copions encore des fichiers entiers dans les images Fedow/LaBoutik.** Leur diff est limité et vérifié, mais une future mise à jour de l’image native ne reprendrait pas automatiquement une nouvelle version des mêmes fichiers : il faudrait refaire la comparaison et réappliquer les seules exceptions choisies. L’absence de montage ne veut donc pas dire absence de fork.

Le gitlink `deploy/Lespass/app` est un contexte de build local alternatif ; la superposition release annule ce build et impose le digest du fork construit par CodeBuild. Les anciens gitlinks/stacks ne sont pas les applications servies par la pipeline courante.

## Configurations et données modifiées par nos outils

Ces outils ne remplacent pas des fichiers TiBillet ; **ils écrivent des données de configuration ou des cartes dans les bases natives**.

| Ajout | But / effets en base | Forme et usage |
| --- | --- | --- |
| Admin commun | Applique identifiant, hash Django et flags admin aux trois applications, réutilise les comptes bootstrap ; refus d’un compte homonyme incompatible | Script hôte `configure-gala-admin.py` via `manage.py shell`, après installation ; secret privé `GALA_ADMIN`, sans mot de passe dans Git |
| Retour de recharge | Met `Place.lespass_domain` sur le domaine canonique après réaffectation du tenant ; évite l’ancien retour Stripe vers une page inexistante | `configure-gala-refill-domain.py`, script hôte à chaque release et contrôle sans écriture au healthcheck |
| Clés Stripe/webhook | Réconcilie les valeurs chiffrées de `Configuration` Fedow avec les secrets fournis à la livraison ; logique de recharge native conservée | `reconcile-fedow-webhook.py`, injecté dans shell Django ; pas une surcouche au serializer |
| Import CSV automatique | Télécharge/valide les lots, refuse les identités contradictoires, ne sélectionne que les cartes absentes, appelle `import_cards` natif dans une transaction, vérifie le résultat | Scripts hôte `import-gala-card-stock.py` et `import_card_stock_fedow.py`. Le second est envoyé sur stdin à `manage.py shell`. **Aucun fichier Python/CSV monté ni nouvelle commande persistante dans Fedow** |
| Catalogue privé S3 | Trois lots : G1 3 510, blanc 1 755, noir 1 755, soit 7 020 cartes. Format natif QR/numéro imprimé/NFC, sans en-tête | `card-stock/uploads/<génération>/<nom>.csv` ; Test valide et fige les octets sous SHA-256, Production reprend exactement ce catalogue |
| Variante Smoke | Mode Stripe test, email admin de test et backend Django dummy ; différences de configuration volontairement imposées pour les essais | `materialize-runtime-env.py`, configuration runtime ; présence du formulaire ne prouve pas un email réel |
| Données Gala initiales | Nom/site/admin, clés d’appairage générées par Gala, création native du catalogue et réglages | Secrets Manager + installateurs ; données privées/variables runtime hors Git |
| SQLite Fedow | Répertoire distinct, copie de sauvegarde cohérente et garde explicite de préparation d’une base vide ; anciens PostgreSQL conservés à part | `fedow-sqlite.py`, outil hôte ; moteur et bloc `DATABASES` Fedow exactement natifs |

Déposer un nouveau CSV ne modifie pas immédiatement le Gala actif. Il faut lancer Test puis sélectionner/promouvoir la release avec son catalogue figé. Retirer un CSV ne supprime pas les cartes déjà en base. Le catalogue `deploy/card-stock.json` est le secours historique/CLI ; la sélection automatique actuelle lit le dossier S3.

Le stock natif importé et la création d’une carte inconnue au scan sont deux fonctions différentes. Une carte enregistrée au scan prend son NFC comme numéro par défaut et un UUID QR interne ; ce mécanisme ne peut pas reconstituer le numéro/QR déjà imprimé d’une carte usine.

## Assemblage et montages restants

Les quatre stacks courantes sont `deploy/{Fedow,Laboutik,Lespass,traefik}` avec leurs fichiers release. Elles remplacent l’assemblage de développement des dépôts amont : réseaux backend séparés, domaine Gala, fichiers runtime par application et images livrées au digest.

Autres écarts d’assemblage observés :

- Volumes nommés de développement remplacés par répertoires hôte pour les bases ; **mêmes moteurs/version de service de référence** : Fedow SQLite, LaBoutik PostgreSQL `11.5-alpine`, Lespass PostgreSQL `13-bookworm`.
- LaBoutik utilise les processus de l’image native dans `laboutik_django`, sans service Celery séparé du Compose amont. Lespass conserve son conteneur Celery distinct ; notre commande omet le `--concurrency=6` du Compose amont et utilise la valeur par défaut.
- Notre service memcached Lespass omet les options amont `-m 256 -I 8m` et utilise les valeurs par défaut. C’est un écart de capacité, sans preuve d’un incident dans cet audit.
- LaBoutik utilise `restart: "no"` dans ses services ; Fedow/Lespass conservent `always`. Le démarrage de l’ensemble est orchestré par notre service systemd. Cela diffère de l’auto-restart du Compose LaBoutik amont.
- Le HTTPS public utilise ACME/Let’s Encrypt et le stockage `acme.json`, à la place du mécanisme mkcert du Compose Lespass de développement. Il s’agit de configuration du proxy, pas de calcul de portefeuille.
- Routage local au Gala via `host-gateway`/Host public, réseaux et noms de services explicites ; anciennes entrées `*.tibillet.localhost` existent encore dans certains Compose.
- Nginx contient nos domaines, alias d’administration LaBoutik `/admin/` → `/adminstaff/`, redirections Lespass `/adminstaff/` → `/admin/`, chemins/port HTTP/WebSocket, resolver Docker et paramètres de proxy/statiques ; ajoute `/source/` et l’en-tête de lien aux sources.

**29 montages sont déclarés, comptés par conteneur et destination, dans les quatre Compose actifs. Aucun ne monte un fichier Python/HTML ou un catalogue CSV.** Les images Redis créent en plus des volumes `/data` implicites ; les déclarations Compose ne suffisent donc pas à compter tous les montages réels Docker.

| Type | Déclarations | Origine et utilisation |
| --- | ---: | --- |
| Bases | 3 | Besoin natif ; organisation de stockage hôte propre au déploiement. SQLite Fedow + deux PostgreSQL |
| `www` médias/statiques | 7 | Besoin de fichiers partagés Django/Celery/Nginx ; utilisés. Les statiques personnalisés sont désormais aussi dans les sources, puis collectés |
| Logs | 7 | Journalisation native et partage avec Nginx/Celery ; utilisés |
| Configuration Nginx | 3 | Montage de configuration utilisé aussi par TiBillet ; **contenu adapté chez nous**, chargé par les proxies |
| Sources publiques `/source` | 3 | **Montage ajouté par nous**, lecture seule de pages/archives de la release ; n’écrase aucun Python ou template Django |
| Backups locaux `/Backup` | 2 | LaBoutik : dumps/cron Borg de l’image native ; Lespass : répertoire conservé, sans besoin pour les sauvegardes S3 |
| SSH/Borg | 2 | Hérités du besoin de sauvegarde distante ; dernier contrôle détaillé : dossiers vides. Pas nécessaires aux sauvegardes S3 |
| Socket Docker | 1 | Traefik découvre les services ; mécanisme présent aussi dans la référence de développement |
| Certificats ACME | 1 | Stockage TLS persistant du proxy public |

Le contrôle SSM du 9 octobre retrouve exactement **31 montages sur Smoke : 29 bind mounts déclarés et deux volumes Redis `/data` implicites**. Aucun des 20 fichiers applicatifs contrôlés n’est recouvert par un montage.

Les deux volumes Redis sont du stockage de broker/tâches TiBillet, pas une injection de code. Emails, rapports, notifications/ventes et impression selon les fonctions configurées peuvent passer par les tâches natives. Cet audit ne mesure pas une file de tâches en attente.

Le fait que le **type** de montage existe chez TiBillet ne signifie pas que chaque chemin/configuration chez nous est identique au Compose vanilla. L’annexe ci-dessous donne toutes les destinations et leur origine dans notre historique.

## AWS, pipeline et exploitation : ajouts propres au projet

Cette couche est la plus importante en nombre de fichiers. Elle est extérieure au métier TiBillet, mais peut évidemment affecter démarrage, connexion entre services, secrets et disponibilité.

| Ensemble | But | Forme / utilisation |
| --- | --- | --- |
| Foundation | Créer/mettre à jour les ressources des Galas sans écraser une instance existante | Terraform, état distant/verrouillage, plan contrôlé, approbation/apply/finalisation ; pipelines dédiées |
| Test | Construire les trois images, sélectionner les CSV, déployer Smoke, contrôler les parcours et sauvegarder une preuve | CodePipeline/CodeBuild, buildspecs, scripts Python/SSM ; lancé pour une version code/catalogue |
| Production par Gala | Valider puis livrer les images/catalogue testés sur une EC2 déterminée | Artefact de release exact, contrôles promotion, approbation, SSM ; nom Production ne veut pas dire que le Gala est public/actif |
| Gala actif | Un même jeu de domaines publics sert le Gala désigné ; bascule d’EIP et marqueur SSM | Pipeline ActiveGala et `switch-active-gala.py`, secrets partagés, contrôles cible ; opération explicite |
| Hôtes | EC2/EBS, security groups, instance profiles/SSM, IP de sortie des inactifs et accès IAM/Identity Center | Terraform/bootstrap. Le réparateur `reconcile-inactive-gala-outbound.py` est une migration ponctuelle manuelle |
| Secrets | Clés propres par Gala et intégrations Stripe test/live, email/admin partagées | Secrets Manager, rendu de fichiers privés sur l’hôte ; ne sont pas des fichiers sources montés |
| Artefacts et sources | ECR pour images, S3 privé pour releases/backups/lots, archives correspondantes publiques GitHub et `/source/` | Outils build/publish ; lecture par livraison et utilisateurs selon le cas |
| Démarrage/reprise | Installe les scripts sous `/usr/local/lib/tibillet-gala`, démarre les quatre stacks au reboot, relance les installateurs et réglages choisis | Bootstrap + unités systemd + scripts hôte ; `reconcile-runtime.py` reste outil d’intervention |
| Contrôles avant/après release | Backup récent, espace libre, cible autorisée, verrou de Gala, digests/labels, domaine/tenant/recharge/email/admin/Celery | `preflight.sh`, validators, `healthcheck.sh` et outils spécialisés ; peuvent bloquer une livraison |
| Sauvegarde/restauration | Deux dumps PostgreSQL et snapshot SQLite, empreintes/métadonnées, upload S3 par Gala, restauration sous garde explicite | Outils hôte + timer toutes les six heures ; le nom historique `backup-postgres.sh` couvre désormais SQLite aussi |
| RAM/disque | Swap de 2 Gio, swappiness 10 ; nettoyage des images Docker inutilisées si réserve disque insuffisante | Scripts hôte pendant installation/livraison ; ne suppriment pas les bases/volumes applicatifs |
| Politiques/coûts | Listes de cibles permises/interdites, budget et règles de conservation des objets/images | YAML/Terraform, utilisés dans les contrôles correspondants ; certains outils de périmètre sont manuels |
| Source/Git | Notices auteurs/AGPL, exclusions de `.git`, `.context`, secrets et données du contexte Docker | `AUTHORS.md`, `NOTICE.md`, README, `.gitignore`, `.dockerignore` ; pas une fonction de caisse |

Le TSV détaille les références littérales des scripts dans les outils/buildspecs/Terraform/systemd. Elles montrent le raccordement, pas le nombre d’exécutions. Absence de référence trouvée n’est pas preuve de « jamais exécuté » : par exemple la publication GitHub des sources est une commande opérateur effectivement documentée par les reçus du 8 octobre.

Les configurations AWS font encore explicitement référence au compte `318629836660`, région `eu-west-3`, projet `tibillet-gala-paris` et domaines Aix. Elles ne constituent pas un installateur générique indépendant du compte/domaine.

## Ce qui est natif ou a été restauré

| Sujet | État actuel face à la référence |
| --- | --- |
| Moteurs de bases Django | Trois blocs `DATABASES` identiques au texte natif ; seul Fedow est SQLite. PostgreSQL pour Lespass/LaBoutik est natif |
| Modèles/migrations Lespass | `BaseBillet/models.py`, `AuthBillet/models.py` et migrations inchangés ; pas de nouvelle table de session/remboursement Gala |
| Paiement/remboursement Lespass | `BaseBillet/views.py` et page native `account/balance.html` inchangés |
| Dépendances Lespass | `pyproject.toml`, `poetry.lock` et licence native inchangés ; différence système Debian décrite plus haut |
| Prix/happy hour | Substitution retirée ; prix natifs de LaBoutik |
| Limite de terminaux | Personnalisation de deux terminaux/FIFO retirée |
| Monnaie cadeau | Option `ENABLE_GIFT_ASSET_SYNC` retirée ; synchronisation native restaurée |
| Fedow transactions | Ancienne copie du serializer retirée ; code natif de l’image et protections de référence sélectionnés |
| Dashboard Fedow | Dashboard natif ; ancien suivi Gala et routes `/dashboard/suivi/` retirés. Accueil réseau public selon natif, détails monnaie/lieu protégés par compte staff actif |
| Fedow PostgreSQL | Bascule/customisation retirée ; ancienne configuration archivée, anciennes données gardées à part. Pas de migration fictive des soldes vers SQLite |
| Écarts LaBoutik hérités | Traitement des billets, validation des adhésions, carte primaire, doublons/erreurs et délais réseau repris au texte natif ; aucune de ces anciennes variantes ne reste dans les copies actives |

Le contrôle [verify-restored-code.py](../features-enlevees/verify-restored-code.py) a été exécuté aujourd’hui : sept unités restaurées exactement identiques, fichiers de vues/validation LaBoutik identiques hors les exceptions NFC/notices déclarées, API native LaBoutik sélectionnée, dashboard/serializer Fedow sans surcharge et SQLite natif. Il est aussi appelé **pendant le build** : ce script et sa recette d’exceptions sous `features-enlevees` ne sont pas une simple archive passive.

## Archives, doublons et outils non automatiques

| Groupe | Contenu et utilisation |
| --- | --- |
| `TECH_DOC/features-enlevees/` | Archives exactes/recettes/reçus des retraits pour une éventuelle réintroduction. Les archives ne sont jamais chargées par les apps ; exception des contrôles de build signalée ci-dessus |
| `deploy/Lespass/legacy-100j-qr-flow/` | Ancien QR et références du remboursement local. Archives hors image/runtime |
| `deploy/Laboutik_100-jours-225/` | Ancienne stack/copies, hors les quatre stacks actuelles ; ne pas lancer pour mettre à jour un Gala courant |
| `deploy/Lespass-v2/` | Ancienne stack et sous-module, hors release actuelle |
| `deploy/Lespass/www/static/…` | Deux copies CSS/JS identiques aux sources intégrées dans `BaseBillet/static`. Désormais doublons ; le mécanisme actif est image → collectstatic → volume partagé → Nginx |
| `deploy/tools/setup*.sh`, `start-stacks-on-boot.sh` | Ancien chemin de setup Infisical/démarrage ; la pipeline actuelle emploie Secrets Manager/bootstrap/systemd |
| `deploy/tools/scripts/` | Anciens outils de reset soldes, suppression de cartes, création de bars, images produits, emojis/recherche/sauvegarde. **Exécutables manuellement et certains destructifs**, mais aucun lancement par la pipeline actuelle trouvé ; aucune commande exécutée dans cet audit |
| `releases/`, `deploy/registry/examples/` | Manifestes anciens et exemples, pas toutes des versions actives simultanément |
| `.claude`, `TECH_DOC`, `deploy/docs` | Conventions, guides, anciens constats et preuves ; les sections historiques doivent être lues avec leur date |
| Tests | Ajouts de non-régression QR/domaines/email/cartes/images/pipeline/sauvegardes. Les tests eux-mêmes ne servent pas les clients |

**Ancien remboursement local 100J : le formulaire IBAN/BIC n’est toujours pas actif dans cette version.** Il ne s’agit pas d’un ajout actif par rapport à vanilla : c’est une ancienne fonction 100J non portée. Le remboursement Stripe natif ne démontre pas une prise en charge automatique des recharges espèces/CB sur place. Ce chantier reste différé ; aucun nouveau système n’a été ajouté pendant l’audit.

## Points de maîtrise à retenir, sans modification dans cet audit

1. Les fichiers complets `settings/views/validators/install` copiés au build restent un point d’attention aux mises à jour natives, même si les anciennes dérives métier ont été retirées.
2. Les personnalisations web masquent des fonctions et contiennent des textes/liens Aix codés en dur. Pour un futur autre Gala, elles ne s’adaptent pas toutes au seul nom configuré.
3. Le mécanisme d’import CSV est **un outil de livraison sur l’hôte appelant l’importeur natif**, pas une nouvelle commande intégrée à l’image Fedow. La création NFC sans QR, elle, est bien intégrée dans LaBoutik.
4. Les montages SSH et `/Backup` Lespass paraissent superflus pour S3 ; `/source` est notre ajout. Nginx reste en configuration montée. Rien de cela ne remplace le serializer Fedow.
5. Certaines documentations décrivent encore une préparation locale ou l’ancien setup Infisical. Par exemple la section « Installation/Mise à jour » de `deploy/README.md` et des phrases de `features-enlevees/README.md` sont historiques. Elles peuvent induire une mauvaise intervention malgré une installation courante correcte.
6. Les versions de PostgreSQL, Redis et certaines images d’infrastructure restent celles héritées de la référence. Cette comparaison ne constitue pas une analyse complète de support/sécurité ni de charge Gala.
7. Le champ historique de manifeste `tibillet_upstream_commit` contient le commit construit du fork dans les preuves récentes ; ce nom ne doit pas servir à déduire la référence OG. Les références natives de comparaison sont celles de ce rapport et `image-sources.json`.
8. Aucun diff seul ne prouve l’absence de panne, de double mouvement ou une couverture complète du remboursement ; les scénarios physiques/paiement/email doivent être distingués des contrôles techniques déjà acquis.

## Vérification réelle des serveurs du 9 octobre

Compte AWS `318629836660`, `eu-west-3`, profil `gala-elevated` vérifiés. Marqueur du Gala actif : **`gala-smoke`** ; EIP **`51.44.90.200`** attachée à `i-0037b98572fccdff2`. Le domaine public ne sert donc pas l’ancienne EC2 Aix, même s’il porte le nom du Gala Aix.

| Gala / EC2 | État AWS actuel | Version/preuve disponible | Inspection interne aujourd’hui |
| --- | --- | --- | --- |
| Smoke / `i-0037b98572fccdff2` | Running, SSM Online, EIP active | `cd677bb3`, release `smoke-cd677bb3…-5f79087e…` | **Oui**, conteneurs/images/sources/montages inspectés |
| Ancienne Aix / `i-0801aa8a2273838aa` | Running, SSM ConnectionLost, aucune IPv4 publique | Dernière pipeline livrée : `gala-am-aix-v1.0.11`, application `3cfd531b`, 3 octobre | **Non**, dernier ping SSM 5 octobre 23:09:39 UTC ; pas de remise en ligne dans cet audit |
| Premier lancement / `i-00cb72994b875e92d` | Stopped | Dernière pipeline de livraison réussie ; ancienne instance de vérification | Non, laissée arrêtée |
| Import cartes / `i-06c4a26b49ac45afa` | Stopped | Dernière pipeline de livraison réussie ; précédente vérification d’import | Non, laissée arrêtée |
| Images/CSV / `i-0824730d4d46b3673` | Stopped | Application `9bece97e` et premier démarrage vérifiés le 8 octobre | Non, laissée arrêtée ; précédents reçus conservés |

### Smoke : ce qui est effectivement installé

Sonde SSM `df51d8a9-0c7c-4b6d-afeb-df16dab31923` : succès. Le checkout et le manifeste déployé portent `cd677bb39cf7efcd43f55cd943d6177fb07cf1ba`. Les images applicatives sont exactement les digests de la dernière preuve Test. Les labels de bases natives/commit Fedow et LaBoutik correspondent aux références auditées. Les 15 conteneurs attendus sont en état `running`.

Vingt fichiers sont comparés par SHA-256 directement dans les conteneurs : dix destinations de copie dans les images ; cinq sources natives conservées (serializer, importeur, vues/routes dashboard Fedow et client Fedow LaBoutik) ; cinq sources du fork Lespass. **Toutes les empreintes correspondent.** Aucun montage ne recouvre ces fichiers. Les 31 montages réels correspondent aux 29 déclarations plus les deux volumes Redis implicites.

Les flags confirment le mode Stripe test de Smoke et le backend email dummy de Lespass/LaBoutik. Ce sont les différences voulues de Smoke, pas une preuve d’envoi SMTP réel. Le manifeste référence 7 020 cartes ; les trois CSV présents dans `card-stock/uploads/` sont retéléchargés en privé et leurs empreintes correspondent exactement aux trois lots du catalogue figé actif. Aucun import n’est relancé et aucune association de carte n’est affichée/publiée.

Le timer de backup est `active`. Les objets de la dernière sauvegarde `20261009T061545Z` sont présents dans S3 : deux dumps PostgreSQL, snapshot SQLite et fichiers d’intégrité/métadonnées. Leur présence ne constitue pas une nouvelle restauration ; la restauration vérifiée du 8 octobre reste la preuve correspondante.

**État historique systemd à signaler :** `tibillet-gala-stacks@gala-smoke.service` est toujours marqué `failed`/exit 254, depuis le **25 septembre à 17:16 UTC**. Les 15 conteneurs actuels tournent et la dernière pipeline Test est réussie ; ce statut n’est donc pas présenté comme une nouvelle panne de ces applications. Le redémarrage via cette unité n’est pas retesté dans l’audit et ne doit pas être annoncé validé aujourd’hui. Aucun reset de l’état ou restart n’est effectué.

### Ancienne Aix : ne pas généraliser l’absence de montages

La dernière pipeline de livraison Aix est réussie et date du 3 octobre. Le manifeste S3 `gala-am-aix-v1.0.11` désigne l’application `3cfd531b4ca3c9953f27ca06b2391cadcf33db00`, avec les images natives Fedow/LaBoutik d’avant leur intégration à nos images dérivées.

Les Compose de ce commit prévoient **18 montages distincts de code/templates** (21 lignes avec trois doublons) : settings/serializer/dashboard/templates Fedow, settings/install/views/validators/client Fedow/templates LaBoutik. Ce constat porte sur la **configuration de sa dernière release livrée**, pas sur une nouvelle inspection de Docker : SSM est déconnecté et la machine n’a pas d’IP publique.

Il serait donc incorrect de dire « aucun montage de code sur toutes les anciennes instances ». Cela est confirmé aujourd’hui sur **Smoke**, et était confirmé sur le **Gala neuf du 8 octobre** ; l’ancienne Aix n’a pas de livraison prouvée des retraits et nécessite un contrôle séparé si elle doit être réutilisée. Cet audit ne change ni son réseau ni ses applications.

## Preuves de livraison existantes et travail restant

Le [test du gala neuf du 8 octobre](2026-10-08-pipeline-images-csv-gala-neuf.md) conserve : build/Test/Production réussis ; premier import de 7 020 cartes puis vérification zéro création ; deux créations NFC inconnues sans doublon à la répétition ; dix sources copiées contrôlées, sans montage les recouvrant ; trois formulaires QR/admin, apex/recharge/Celery validés ; backups et restauration isolée des trois bases réussis. Le Gala neuf a ensuite été arrêté avec ses données conservées. Smoke était le Gala actif. Ces preuves ne disent pas que les anciennes EC2 Aix ont été toutes mises à la même release.

Limites conservées : aucun paiement Stripe réel, aucun lecteur physique et aucun email réel exercé pendant ce nouveau test ; formulaires admin contrôlés mais connexion par mot de passe non soumise dans ce test. Les confirmations physiques antérieures des colonnes des cartes ne remplacent pas un essai matériel sur ce Gala neuf.

Travail restant dans l’ordre :

1. Avant réutilisation d’Aix, rétablir séparément son accès d’inspection puis vérifier sa version/montages ; cet audit n’autorise pas implicitement une remise en ligne ou un déploiement. Avant de garantir la reprise au reboot de Smoke, vérifier aussi le chemin systemd dont l’état d’échec historique subsiste.
2. Si une simplification supplémentaire est souhaitée, choisir explicitement parmi les écarts restants à partir de cet inventaire ; ne pas confondre retrait d’un volume avec retrait de la fonctionnalité.
3. Avant usage réel, achever les scénarios paiement/email/lecteur et le chantier de remboursement local déjà identifié. Cet audit n’en annonce pas la réussite.

## Annexes exhaustives

- [Tous les chemins, forme, utilisation, historique et empreintes](2026-10-09-differences-vanilla-fichiers.tsv).
- [Preuves structurées : références, copies d’images, montages, blocs natifs, HTTP, reçus](2026-10-09-differences-vanilla-preuves.json).
- [Diff du code Lespass et des dix destinations Fedow/LaBoutik](2026-10-09-differences-vanilla-code.diff).
- Les 40 fichiers couverts par `2026-10-03-fork/ALL_SHA256SUMS` ont été revérifiés inchangés. Les anciens audits restent conservés, sans réécriture rétroactive.

### Tous les montages déclarés

| Stack / conteneur | Source hôte → destination | Mode | Type | Première apparition dans le fork |
| --- | --- | --- | --- | --- |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./sqlite-database` → `/home/fedow/Fedow/database` | rw | base persistante | `a219b5d6` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./www` → `/home/fedow/Fedow/www` | rw | médias/statiques générés | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./logs` → `/home/fedow/Fedow/logs` | rw | logs | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./www` → `/www` | rw | médias/statiques générés | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./logs` → `/logs` | rw | logs | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./nginx` → `/etc/nginx/conf.d` | rw | configuration Nginx | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `../source/public` → `/source` | ro | sources publiques ajoutées Gala | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_postgres` | `./database/data` → `/var/lib/postgresql/data` | rw | base persistante | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./www` → `/DjangoFiles/www` | rw | médias/statiques générés | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./logs` → `/DjangoFiles/logs` | rw | logs | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./backup` → `/Backup` | rw | sauvegardes locales | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./ssh` → `/home/tibillet/.ssh` | rw | configuration SSH/Borg | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./www` → `/DjangoFiles/www` | rw | médias/statiques générés | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./logs` → `/DjangoFiles/logs` | rw | logs | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./nginx` → `/etc/nginx/conf.d` | rw | configuration Nginx | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `../source/public` → `/source` | ro | sources publiques ajoutées Gala | `01ca8349` |
| `deploy/Lespass/docker-compose.yml` / `lespass_postgres` | `./database` → `/var/lib/postgresql/data` | rw | base persistante | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./www` → `/DjangoFiles/www` | rw | médias/statiques générés | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./logs` → `/DjangoFiles/logs` | rw | logs | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./backup` → `/Backup` | rw | sauvegardes locales | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./ssh` → `/home/tibillet/.ssh` | rw | configuration SSH/Borg | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_celery` | `./www` → `/DjangoFiles/www` | rw | médias/statiques générés | `e2ad1406` |
| `deploy/Lespass/docker-compose.yml` / `lespass_celery` | `./logs` → `/DjangoFiles/logs` | rw | logs | `e2ad1406` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `../source/public` → `/source` | ro | sources publiques ajoutées Gala | `01ca8349` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./www` → `/www` | rw | médias/statiques générés | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./logs` → `/logs` | rw | logs | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./nginx` → `/etc/nginx/conf.d` | rw | configuration Nginx | `bc5b1a85` |
| `deploy/traefik/docker-compose.yml` / `traefik` | `/var/run/docker.sock` → `/var/run/docker.sock` | ro | socket Docker | `bc5b1a85` |
| `deploy/traefik/docker-compose.yml` / `traefik` | `./acme.json` → `/acme.json` | rw | certificats | `bc5b1a85` |
