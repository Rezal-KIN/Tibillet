# Gala et installation officielle TiBillet — comparaison du 9 octobre 2026

Cet audit complète, sans le remplacer, [l'inventaire exhaustif du dépôt et des serveurs](2026-10-09-differences-vanilla.md). Il distingue une installation de serveur **décrite par TiBillet** des Compose de développement présents dans ses dépôts. Aucune application, instance Aix ni pipeline existante n'est modifiée pendant cette comparaison.

L'[investigation ciblée du domaine racine et de Nginx](2026-10-09-domaine-racine-et-nginx.md), réalisée ensuite, complète les conclusions ci-dessous : le tenant racine est cohérent, mais le worker Celery ne résout pas son endpoint Fedow local, certains échanges restent dirigés vers l'EC2 publique active et plusieurs domaines secondaires ne sont pas routés. Elle rectifie aussi une erreur de sonde sur la persistance du bouton recharge dans le témoin manuel.

## Référence correcte

Le guide officiel des trois moteurs est [server_install.md](https://github.com/TiBillet/documentation_v2/blob/1dc42966228e535a1a5a4f4a7a373323b6234a7c/docs/install/server_install.md), commit `1dc42966228e535a1a5a4f4a7a373323b6234a7c`. Il décrit Fedow, Lespass, LaBoutik et demande Docker/Compose, un reverse proxy, un domaine et un compte Stripe Connect. Pour un serveur de test réunissant les trois, minimum indiqué : 2 vCPU / 4 Go de RAM. Le chemin web historique redirige vers une page 404 ; le contenu officiel Git est conservé comme référence.

Deux comparaisons sont différentes et doivent rester séparées :

- **Fonctionnement/configuration serveur** : guide officiel et expérience sur EC2 neuve avec les images `latest` qu'il prescrit.
- **Nos modifications applicatives** : versions amont exactes des images et du fork déjà adoptées, documentées dans l'audit précédent. Une différence entre le `latest` d'aujourd'hui et notre ancienne version ne prouve pas un patch de notre part.

## Les montages, ligne par ligne

Sur Smoke, les 31 montages effectivement inspectés se décomposent en **22 prescrits dans le guide + 2 créés implicitement par les images Redis + 7 absents des trois Compose du guide**. Parmi ces 7, deux servent au reverse proxy que le guide exige sans fournir son fichier Compose. Il ne reste aucun montage de fichier Python ou HTML sur Smoke.

Le [TSV des 31 montages](2026-10-09-montages-guide-officiel.tsv) donne conteneur, source, destination, lecture seule et ligne du guide correspondante. Le comptage concerne chaque couple conteneur/destination : un dossier partagé par deux conteneurs compte deux fois.

| Groupe | Nombre | Présent dans le guide ? | Ce qu'il fait / usage actuel | Conclusion proposée |
| --- | ---: | --- | --- | --- |
| Bases Fedow, Lespass, LaBoutik | 3 | Oui, lignes 212, 399, 667 | Conserve SQLite Fedow et PostgreSQL Lespass/LaBoutik après remplacement du conteneur. Fedow utilise chez nous le dossier `sqlite-database`, même destination interne et moteur natif. | Garder ; données persistantes natives. |
| Statiques/médias Django et Nginx | 6 | Oui | Partage les fichiers collectés/téléchargés entre application et serveur web. Le code Python/HTML n'y est pas monté. | Garder ; modèle du guide. |
| Logs Django et Nginx | 6 | Oui | Journaux des services et des proxys sur l'hôte. | Garder ; modèle du guide. |
| Configurations Nginx | 3 | Oui, lignes 233, 478, 728 | Nginx lit les règles de routage. **Le montage est natif, le contenu est personnalisé** : domaines, administration, sources, résolution/transport local et réglages proxy. | Garder le montage ; revoir les différences de contenu séparément. |
| `/Backup` Lespass et LaBoutik | 2 | Oui, lignes 430, 697 | Sauvegarde locale native ; LaBoutik conserve son cron. Notre sauvegarde S3 est un mécanisme distinct. | Ce ne sont pas nos ajouts. Lespass paraît facultatif avec S3 ; suppression éventuelle après contrôle du chemin natif. |
| SSH/Borg Lespass et LaBoutik | 2 | Oui, **optionnels**, lignes 431, 698 | Clés pour sauvegarde Borg par SSH. Dossiers constatés vides ; S3 ne les utilise pas. | Retrait possible pour une installation n'utilisant pas Borg, sans prétendre qu'il s'agit de patches métier. |
| Redis `/data` | 2 | Images natives du guide, pas de déclaration Compose | Stockage des brokers/cache/tâches. Volumes anonymes créés par les images Redis, sans code ajouté. | Garder le mécanisme natif ; décision de persistence distincte. |
| `/source` dans les trois Nginx | 3 | **Non — ajout de notre projet** | Publie en lecture seule pages/archives des sources de la release. N'écrase aucun fichier applicatif. | Conserver un accès aux sources. Pour enlever ce montage, comparer le coût d'une image Nginx construite par release ou d'une publication externe ; aucune modification effectuée. |
| `www` dans `lespass_celery` | 1 | **Non — ajouté par nous** | Le worker partage les fichiers avec Django/Nginx. Introduit avec le partage des logs le 26 septembre, commit `e2ad1406`. | Justification à préciser selon les tâches utilisant ces fichiers ; pas de retrait aveugle. |
| `logs` dans `lespass_celery` | 1 | **Non — ajouté par nous** | Rend les journaux du worker persistants et consultables avec ceux de Django. Même commit `e2ad1406`, intitulé « Share Lespass logging volume with Celery worker ». **Test natif : sans montage, le worker redémarre en boucle sur `/DjangoFiles/logs/Djangologfile` absent.** | Garder une préparation correcte du dossier de logs. Ce montage est une solution simple, sans remplacement de code ; son retrait exigerait une autre préparation/persistence. |
| Socket Docker dans Traefik | 1 | Reverse proxy demandé ; montage exact non fourni par ce guide | Notre Traefik découvre les services via les labels Docker ; socket en lecture seule. | Nécessaire à cette configuration du proxy ; pas au métier cashless. Une autre configuration aurait un coût de maintenance. |
| `acme.json` dans Traefik | 1 | Reverse proxy HTTPS demandé ; montage exact non fourni par ce guide | Conserve les certificats/compte ACME entre recréations. | Garder avec ce proxy ; suppression = perte de sa persistence TLS. |

Il est donc incorrect de dire « tout est intégré dans les images », et également incorrect de dire « tous les volumes ont été ajoutés par nous ». Les **5 montages supplémentaires au niveau des trois applications** sont `/source` × 3 et `www/logs` Celery × 2. Les **2 autres** appartiennent à notre mise en place du reverse proxy requis.

## Corrections de lecture de l'audit précédent

Les montages de base en répertoires hôte ne sont pas un remplacement anormal de volumes nommés : le **guide serveur prescrit déjà ces bind mounts**. Les volumes nommés figuraient dans certaines références de développement.

La commande Celery Lespass sans `--concurrency=6`, memcached Lespass sans `-m 256 -I 8m` et LaBoutik sans conteneur Celery séparé correspondent au **guide serveur**. Ces différences étaient réelles face à certains Compose de dépôt, mais ne constituent pas des personnalisations face à cette installation officielle. Les versions PostgreSQL 13/11.5 et Redis 7.2.3/6 de notre assemblage sont celles indiquées dans ce guide.

## Toutes les familles de différences actives

« Image » signifie que la modification est embarquée au build ; cela reste une modification du code, même sans volume. « Outil hôte » signifie commande pendant installation/livraison, hors serveur applicatif permanent. L'annexe exhaustive antérieure conserve tous les chemins et diffs.

| Différence | Forme | Effet / utilisation | Proposition avant choix utilisateur |
| --- | --- | --- | --- |
| Parcours QR, inscription/liaison/connexion | Code et templates Lespass dans l'image du fork | Nouvelle entrée `/qr/<uuid>/`, appels natifs et preuve email selon l'état de la carte/du compte. | Garder, besoin exprimé. |
| Identité visuelle et guide d'accueil | CSS, JS, images, police et templates dans Lespass | Apparence Gala et explications cashless. Contient encore textes/liens Aix fixes. | Garder ; paramétrer les libellés lors d'un futur autre événement. |
| Menus masqués | CSS/JS dans l'image | Masque agenda, adhésions, réservations, langue/thème. Ce n'est pas uniquement un changement de couleurs. | Choisir explicitement ce qui doit être accessible. |
| Cartes NFC inconnues sans QR | Deux fonctions LaBoutik dans l'image dérivée | Crée/retrouve une carte absente après confirmation native ; pas sur simple panne réseau. | Garder, besoin exprimé ; tests physiques distincts de la présente comparaison. |
| Import des lots CSV/S3 | Outils hôte, données privées S3, appel de l'importeur **natif** Fedow | Test fige le catalogue, release importe les cartes absentes. Aucune commande import personnalisée persistante ni CSV monté dans Fedow. | Garder ; c'est notre raccordement à la pipeline, extérieur au métier natif. |
| Entrée d'admin par mot de passe et admin commun | Petite modification Lespass + alias Nginx + outil hôte écrivant les comptes natifs | Accès voulu aux trois administrations et compte configuré depuis le secret runtime. | Garder si confirmé ; aucun secret dans cet audit. |
| Tenant sur le domaine racine et bouton recharge | Commandes Lespass de configuration | Modifie les domaines/champs natifs, sans nouveau modèle de paiement. | Garder pour le parcours actuel ; le guide utilise par défaut un sous-domaine de tenant. |
| Domaine de retour Stripe / clés webhook | Outils hôte de réconciliation | Configure les champs natifs pour le retour canonique et les clés du Gala. | Garder les champs cohérents ; paiement réel non démontré par cet audit. |
| Transport local Lespass → Fedow | Client Lespass modifié dans l'image + réseaux | Le serveur web contacte son propre Fedow. **Le worker Celery sélectionne la même adresse mais ne peut pas la résoudre**, faute de réseau partagé. | Corriger la configuration réseau minimale avant de considérer cette adaptation complète ; retour au HTTPS natif à tester sur une instance inactive neuve. |
| Résolution locale des domaines publics | `extra_hosts` des Compose release, configuration Nginx | Lespass → Fedow et LaBoutik → Lespass/Fedow ont des correspondances locales. **Lespass → LaBoutik et Fedow → Lespass restent dirigés vers l'EIP active.** | Compléter et tester les échanges et TLS sur un Gala inactif ; ce n'est pas un montage de code. |
| TLS/SSL et backend email configurables | Settings Lespass/LaBoutik dans les images | Interprète les booléens et permet le backend sans envoi en test. | Garder le correctif minimal ; SMTP réel reste un test distinct. |
| Logs de connexion réduits | Petite modification Lespass | Évite d'inscrire le lien magique complet dans les logs. | Garder. |
| Installateur LaBoutik reprenable | Une fonction dans l'image dérivée | Reprend un appairage déjà réussi et limite les réinvitations au redéploiement. | Utile à la pipeline ; comparer au démarrage natif, ne pas retirer avant décision. |
| Liens et archives de sources | Templates/settings/images + Nginx + `/source` | Accès au code correspondant aux images livrées ; aucun ancien dashboard financier. | Garder l'accès, discuter l'emballage. |
| Images construites et identifiées | Dockerfiles, digests ECR, labels, gardes de build | Lespass fork, Fedow/LaBoutik dérivés de digests natifs. Dix destinations `COPY` dont neuf sources uniques. | Garder la reproductibilité ; comparer les fichiers entiers à chaque mise à jour amont. |
| Base système du build Lespass | Dockerfile `python:3.11-bookworm` | Diffère de la base `bullseye` de la référence initiale ; dépendances Poetry inchangées. | Écart de construction à identifier, distinct des fonctionnalités. |
| Redémarrage LaBoutik | Compose `restart: "no"` + orchestration systemd | Guide : `always`. Chez nous, Docker ne relance pas automatiquement ces cinq services après un arrêt/crash ; une intervention/orchestration doit le faire. | Priorité de disponibilité : retour à `always` à proposer. Pas changé pendant audit. |
| HTTPS/ports/alias/source/règles Nginx | Fichiers de configuration montés | Notre contenu adapte le domaine unique, l'administration, les sources et les communications. | Séparer paramètres nécessaires et surplus ; aucun calcul de solde. |
| Paramétrage des Galas | Secrets Manager, rendu `.env`, modèles natifs | Noms, domaines, Stripe, email, admins et appairages. Smoke volontairement en test Stripe et backend email sans envoi. | Ne pas confondre identité de code avec valeurs identiques de test et de production. |
| Variables PostgreSQL résiduelles dans Fedow | Variables runtime `POSTGRES_USER/DB/PASSWORD` | Encore injectées sur Smoke, alors que le bloc de base Fedow natif utilise SQLite. Elles ne changent pas ce moteur. | Nettoyage possible du rendu d'environnement, séparé des données PostgreSQL archivées. |
| AWS, pipeline, bascule active | Terraform, CodePipeline/CodeBuild, EC2/SSM/ECR/S3, scripts hôte | Automatise construction, premier lancement, promotion et choix de l'EC2 derrière les domaines. | Couche entièrement ajoutée, à garder si l'objectif reste le lancement par pipeline. |
| Sauvegardes, restauration, gardes, swap | Outils hôte et timers systemd | S3 toutes les six heures, SQLite + dumps PostgreSQL, contrôles de livraison, swap 2 Gio chez nous contre exemple 4 Go du guide. | Garder sauvegardes/gardes ; mesurer les besoins mémoire plutôt que conclure sur le seul diff. |
| Documentation, tests, archives | Fichiers du dépôt ; quelques gardes exécutées au build | Historique des retraits et preuve de restauration native. Archives hors application. | Garder les preuves ; distinguer scripts actifs des archives. |

Le dashboard financier personnalisé, le serializer Fedow personnalisé, PostgreSQL Fedow, le toggle de monnaie cadeau, les anciennes variantes billets/adhésions/cartes LaBoutik sont **retirés de la version Smoke actuelle**. Le dashboard natif Fedow reste fourni par son image.

## Smoke et ancienne Aix : cohérence à traiter après choix

Smoke est l'EC2 actuellement servie par les domaines Aix, version `cd677bb3`, avec images actuelles et les 31 montages ci-dessus. L'ancienne EC2 Aix est distincte ; sa dernière release livrée est `gala-am-aix-v1.0.11` / `3cfd531b`. Sa dernière configuration contient 18 destinations de montage de code/template personnalisées. SSM est déconnecté : leur présence dans ses conteneurs **aujourd'hui** n'est pas inspectable et n'est pas présentée comme observée.

Le souhait de cohérence porte sur les mêmes images, Compose, scripts et mécanismes de configuration, avec les valeurs propres au Gala. Ne pas recopier les bases, les clés ou le mode email dummy de Smoke pour prétendre rendre Aix identique.

Le service de démarrage systemd Smoke conserve un état `failed` historique du 25 septembre malgré les conteneurs actuellement démarrés. Le bon démarrage au reboot n'est donc pas confirmé par leur seul état `running`. Ce point et `restart: "no"` doivent entrer dans la vérification de disponibilité avant la version finale.

## Installation indépendante sur EC2 neuve

EC2 temporaire créée pour cet audit uniquement : `i-02df1631672881103`, Ubuntu 24.04.4 amd64, `t3.medium`, disque gp3 40 Gio, profil IAM nouvellement créé avec seulement `AmazonSSMManagedInstanceCore`. Aucun accès aux secrets Gala accordé. Docker 29.1.3, Compose 2.40.3, swap 4 Go. Aucun démarrage depuis notre Terraform/CodePipeline ni image Gala.

Les trois Compose et les règles Nginx sont copiés du guide sans patch applicatif. Le proxy nécessaire est installé séparément avec une image Traefik officielle ; le guide ne fournit pas son Compose. Les secrets locaux sont nouveaux. Aucun CSV/card ni compte de paiement/email Gala n'est repris. L'absence de compte Stripe Connect et SMTP de test valide limite la preuve fonctionnelle et doit être consignée, pas contournée par un faux succès.

### Résultat du démarrage strictement décrit par le guide

Les sept fichiers de configuration installés (trois Compose, trois règles Nginx, proxy séparé) ont leur empreinte contrôlée. Les six premiers correspondent exactement aux extraits du guide. Les 15 conteneurs sont créés ; **26 montages réels** : 22 prescrits + 2 Redis implicites + 2 proxy. Comparés à ce témoin, Smoke a donc **5 montages applicatifs supplémentaires** : trois `/source`, deux Celery. Le proxy construit pour le témoin a les mêmes deux types de montage que notre proxy.

Ce premier démarrage n'est **pas une installation fonctionnelle validée** :

- Fedow refuse l'installation sans `STRIPE_KEY` ou `STRIPE_KEY_TEST` ; une clé vide ne satisfait pas les prérequis du guide. Son conteneur redémarre.
- Celery Lespass redémarre sur `FileNotFoundError: /DjangoFiles/logs/Djangologfile`. Ce défaut de préparation du worker est constaté avec le Compose officiel, indépendamment de nos patches.
- Le `start.sh` natif Lespass a l'appel `manage.py install` commenté. Les migrations sont conditionnées par `MIGRATE` chargé depuis `VERSION`. La base neuve ne contient pas `Customers_domain` et les pages renvoient 500. Le guide « compose up puis visiter » ne décrit donc plus toutes les étapes nécessaires avec ce `latest`.
- Fedow/LaBoutik renvoient 502 ; appairage et fonctions de paiement/email non validés. Le HTTPS du proxy de test répond ; cela ne prouve pas que les applications sont prêtes.

Après conservation de cet état initial, une sonde distincte utilise **la commande native** `migrate_schemas`, qui réussit, puis tente l'installateur natif, qui refuse l'absence de clé Stripe (`Need Stripe Api Key`). La première création du dossier de logs par `docker exec` n'a pas pu entrer dans le worker en redémarrage. Une seconde sonde prépare ce seul dossier dans la couche writable du conteneur et redémarre le worker : il annonce ensuite **ready**, sans nouveau montage ni patch source. Les anciennes erreurs restent dans l'historique des logs, mais le compteur de redémarrage après cette intervention est nul. Aucun source applicatif ni Compose n'est réécrit. Ces résultats ne sont pas présentés comme un démarrage réussi du seul guide.

### Comparaison des fichiers effectivement fournis par les images

Inventaires par chemin, taille et SHA-256, hors `.git`, dépendances installées, données, médias collectés, secrets, logs et bytecode. Les métadonnées privées de l'expérience sont conservées sous `.context/vanilla-manual-20261009/`. Le [TSV des différences d'images](2026-10-09-comparaison-images-fichiers.tsv) distingue patches, contenu ajouté, version amont et fichiers de fonctionnement.

| Application | Fichiers du témoin | Fichiers Smoke | Constats précis |
| --- | ---: | ---: | --- |
| Fedow | 179 | 180 | **178 fichiers identiques**, un `settings.py` modifié et un template admin ajouté. Image `latest` identique au digest natif de notre base : comparaison directe fiable. Serializer, dashboard, importeur et autres sources identifiés restent natifs. |
| LaBoutik | 702 | 704 | **695 fichiers identiques**, sept modifiés et un template admin ajouté. Le deuxième ajout est `celerybeat-schedule`, fichier produit au fonctionnement, pas une fonctionnalité. Image `latest` identique au digest natif de notre base. |
| Lespass | 1 478 | 1 790 | **1 437 identiques**. Dix-sept fichiers portent nos modifications, 323 chemins sont ajoutés au contenu de l'image (majoritairement documentation/déploiement/releases), treize diffèrent à cause de la version amont du `latest`. Dix autres différences d'absence concernent contenu amont/de construction et une absence concerne `celerybeat-schedule`. Ne pas les présenter comme dix suppressions de fonctionnalités de notre part. |

Les treize fichiers Lespass de version amont touchent notamment l'admin tenant, les widgets/cartes géographiques, des templates, tests, `CHANGELOG` et `VERSION`. Ils ne font pas partie de nos patches face à la référence de fork. Cette expérience révèle ainsi une **différence de version réelle avec `latest`**, distincte de notre liste de personnalisations.

Les noms des variables d'environnement ont été comparés sans divulguer leurs valeurs. Les ajouts Smoke portent notamment `GALA_APEX_TENANT`, `GALA_LOCAL_FEDOW`, email TLS/SSL/backend, clés de test/webhook et identifiants d'exploitation ; les variables Borg du guide ne sont pas injectées sur LaBoutik Smoke. Fedow garde les variables PostgreSQL résiduelles signalées plus haut.

**Limite de la première phase, conservée comme résultat historique.** À ce stade, le compte Stripe Connect et SMTP valides étaient des prérequis externes manquants ; aucun secret Gala n'avait été lu pour cette première EC2. L'inventaire de fichiers, montages et configuration était terminé. La seconde phase ci-dessous utilise la configuration TEST et email ensuite autorisée par l'utilisateur et complète la preuve d'appairage et de recharge ; elle ne valide pas exhaustivement toutes les fonctions TiBillet.

Le lancement d'un deuxième agent modèle a échoué avant travail (modèles configuré et défaut refusés par le CLI). La préparation/installation est poursuivie par l'agent principal ; aucun travail parallèle d'un autre modèle n'est prétendu. La question d'utilisation de GPT-5.5 pour ce seul agent est en attente.

### Nettoyage confirmé

EC2 témoin `i-02df1631672881103` : **terminated**. Volume racine `vol-03eb2ad057389c91f` supprimé par `DeleteOnTermination`. Security group `sg-030a5e91c9ea503be`, profil d'instance et rôle IAM temporaires `tibillet-gala-paris-vanilla-audit-20261009-ssm` supprimés. Aucun EIP, DNS, secret Gala ou ressource préexistante n'a été changé. Smoke et l'ancienne Aix restent dans leur état précédent.

Les [preuves synthétiques et le reçu de nettoyage](2026-10-09-comparaison-installation-preuves.json) conservent digests d'images, empreintes des configurations, comparaison des noms de variables, comptes de fichiers et décisions de périmètre. Les inventaires complets et reçus SSM restent privés dans `.context/vanilla-manual-20261009/`.

## Seconde phase : intégrations TEST et parcours natif

Après accord utilisateur, une **seconde EC2 neuve** `i-073379a9933c3ea11` a été installée manuellement, hors pipeline : Ubuntu 24.04.4, `t3.medium`, gp3 chiffré 40 Gio. Son rôle temporaire permettait SSM et la lecture des seuls secrets Gala Stripe TEST et email autorisés. Les clés ont été lues sur l'EC2, sans copie de leur contenu dans cet audit. Aucun secret Stripe LIVE, appairage Gala ou fichier réel de cartes n'a été réutilisé. Le domaine temporaire était propre au témoin ; les domaines Aix/Smoke sont restés en place.

Les images natives, trois Compose et trois fichiers Nginx sont les mêmes qu'en première phase. Le contrôle final retrouve **26 montages**, **15 conteneurs running**, zéro redémarrage automatique comptabilisé après préparation. Les fichiers exécutés correspondent exactement aux sources des images : **179 Fedow, 1 478 Lespass, 702 LaBoutik**, aucun modifié ni manquant. La seule addition de fonctionnement est `celerybeat-schedule` dans LaBoutik. Les sept configurations de Compose/Nginx/proxy gardent leur empreinte initiale. Aucun fichier Python ou HTML n'a été remplacé ou monté sur le code natif.

### Étapes nécessaires, distinctes du seul « docker compose up »

| Étape appliquée au témoin | Forme | Résultat et portée |
| --- | --- | --- |
| Migrations puis installation Lespass | Commandes natives `migrate_schemas --executor=multiprocessing` et `manage.py install` | Création des schémas/domaines puis appairage Fedow ; compense les étapes manquantes du guide avec son image actuelle, sans réécriture de l'installateur. |
| Répertoire des logs Celery | Création du seul `/DjangoFiles/logs` dans la couche writable, puis redémarrage du worker | Worker prêt et répondant au ping. Pas de volume ni de patch ajouté. Cette préparation serait à refaire à la recréation de ce conteneur ; elle ne constitue donc pas une solution durable de pipeline. |
| SMTP STARTTLS | Valeurs natives `.env` : `EMAIL_USE_TLS='1'`, `EMAIL_USE_SSL=''` | Authentification SMTP et un message de test accepté par le backend Django natif. La valeur chaîne `'0'` aurait été vraie dans les anciens settings. Le réglage correct suffit pour ce cas, sans modifier le code email. |
| Retour et webhook Stripe TEST | Nouvelle destination webhook vers **ce témoin**, secret de signature dans son `.env` natif | Événement `checkout.session.completed` reçu, HTTP 200. Aucun webhook Gala existant modifié. Le guide ne configure pas à lui seul cette destination. |
| Bouton recharge | Réglage natif : `Configuration.force_show_refill_button=True`, avec `hide_refill_button=False` | **Rectification : `show_refill_button` est une méthode.** La sonde du témoin a masqué cette méthode au lieu d'établir le réglage persistant ; sa preuve de persistance est invalide. Le bouton visible et le paiement restent observés. Notre pipeline utilise déjà le champ correct, vérifié sur Smoke. |
| Carte de démonstration | Commande native `import_cards` sur un CSV fictif d'une ligne, puis liaison par les méthodes natives Lespass/Fedow | Une carte et un portefeuille de test ; aucune reprise des lots utilisateurs. La liaison est une fixture préparée par API, pas une preuve du parcours d'inscription d'un nouveau porteur. |

Ces étapes ne doivent pas être présentées comme des personnalisations du métier. Elles montrent ce qui relève d'une configuration ou d'une préparation d'installation, et ce qui nécessite actuellement une prise en charge de premier démarrage.

### Fonctions réellement vérifiées

| Contrôle | Preuve obtenue | Limite |
| --- | --- | --- |
| Appairage Lespass ↔ Fedow ↔ LaBoutik | `can_fedow` vrai côté Lespass et LaBoutik, connexion Lespass renseignée côté LaBoutik | Ne remplace pas une vente sur un terminal physique. |
| Importeur TiBillet | Import natif d'une carte fictive, QR et NFC dans les colonnes attendues | L'import automatique S3 de notre pipeline n'est pas exécuté par ce témoin vanilla. |
| QR natif d'une carte déjà associée | Ouverture dans Chrome → session du porteur → `/my_account/` | Aucun lecteur NFC physique ni nouvelle inscription/validation email du porteur testé. |
| Recharge depuis l'interface native | Clic « Recharger en TiBillets » → Stripe Checkout TEST → carte fictive → retour `/my_account/` avec « Tirelire rechargée » | **1 € fictif**, aucun argent réel. La création d'un Checkout par sonde a aussi laissé une session non payée, ensuite expirée. |
| Écriture financière de cette recharge | Session Stripe `livemode=false`, `payment_status=paid`, montant 100 centimes ; Fedow contient **un seul crédit de 100 centimes vers le portefeuille** | Le checkout a deux écritures natives au total, création et transfert. Deux écritures de chaîne ne signifient pas deux crédits au porteur. |
| Rejeu du retour de paiement | Deux appels supplémentaires au callback natif rendent 302 vers le compte ; même solde et mêmes écritures avant/après | Couvre le rejeu de cette recharge ; pas un test de charge ni de toutes les courses concurrentes. |
| Solde visible | Tableau de la tirelire : **1,00 TiBillets** | La liste est chargée par `hx-trigger="revealed"` lorsque sa section apparaît à l'écran. Le placeholder initial et l'écran transitoire ne sont pas établis comme une panne. |
| Email natif | Authentification STARTTLS réussie ; backend SMTP Django natif : un message accepté | Réception dans la boîte et clic du lien de validation non vérifiés. Le connecteur Gmail demandait une reconnexion. |
| Disponibilité HTTP | Accueil/tenant, dashboard et `helloworld` Fedow : 200 ; login natif LaBoutik `/adminstaff/login/` : 200 | Ni connexion interactive complète aux trois administrations ni remboursements/billets/adhésions validés. |

Le [relevé de la seconde phase](2026-10-09-installation-native-integrations-preuves.json) conserve les résultats, empreintes et reçus de nettoyage sans clés, liens de connexion ni identifiants de porteurs réels. La capture du solde est conservée dans `.context/vanilla-integrations-20261009/native-balance-proof.png`. Les commandes et inventaires privés de cette phase restent sous `.context/vanilla-integrations-20261009/`.

**Rectification après inspection du contrat natif :** la sonde de réglage recharge assignait `show_refill_button=True`, alors que ce nom désigne une méthode. Cette affectation peut masquer la méthode sur l'objet Python ou dans son cache ; elle ne configure pas le champ persistant `force_show_refill_button`. Les anciennes sorties sont conservées comme historique d'une sonde incorrecte, et ne prouvent ni une activation durable du bon réglage ni un échec de `Configuration.save()` natif. La sérialisation de la méthode pouvait également faire échouer une sonde. La recharge TEST, son crédit unique et le rejeu sont des observations séparées qui restent valides. La persistance du bouton dans le témoin manuel devra être vérifiée avec le bon champ lors d'un prochain témoin. Voir les preuves et le contrôle actuel de Smoke dans l'[investigation ciblée](2026-10-09-domaine-racine-et-nginx.md).

### Nettoyage de la seconde phase confirmé

EC2 `i-073379a9933c3ea11` : **terminated** ; disque `vol-06b555cd2e33753a2` supprimé. Groupe réseau `sg-0b9231ef3fadb0846`, profil et rôle IAM `tibillet-gala-paris-vanilla-test-20261009-ssm` supprimés, y compris sa permission temporaire de lecture des deux intégrations.

Sur Stripe TEST, **le seul webhook créé pour ce témoin** est supprimé, son prix et son produit sont archivés, et la seule session de Checkout encore ouverte est expirée. Le paiement fictif réussi reste dans l'historique sandbox. Aucun objet Stripe de Gala préexistant n'a été modifié. Aucun EIP ou DNS existant n'a été changé.

### Conclusion pour les choix à faire

La **recharge native, son retour et sa protection contre le rejeu ont fonctionné** sur cette installation indépendante sans nos patches. Le choix d'un domaine propre au témoin évite aussi le besoin de notre transport local destiné aux Galas qui partagent le domaine public. Cela ne démontre pas que ce transport puisse être retiré de l'architecture actuelle sans changer son routage.

Le correctif de booléens SMTP n'est pas nécessaire au cas testé si l'environnement est rendu avec SSL vide et TLS actif. Le code natif propose bien un champ pour forcer le bouton recharge ; sa persistance dans le témoin manuel n'a pas été correctement testée. Notre pipeline utilise ce champ correctement, vérifié sur Smoke. Ces constats permettent de discuter des retraits simples sur la version finale, avant toute modification.

Les problèmes de préparation du premier démarrage Lespass/Celery sont reproduits avec les sources natives et restent à traiter dans l'automatisation. Les cinq montages applicatifs supplémentaires de Smoke restent ceux identifiés plus haut ; aucun nouveau montage ne résulte de ce test. **Aix, Smoke et les pipelines n'ont pas été modifiés.**

## Ordre des décisions et du travail restant

1. Corriger les défauts de communication relevés dans l'investigation ciblée, décider des domaines secondaires utiles et des personnalisations/montages à conserver ; traiter aussi le redémarrage automatique LaBoutik et le démarrage systemd. Garder le code choisi identique entre les Galas, avec leurs valeurs runtime propres.
2. Après ces choix, aligner Aix sur la version retenue, puis vérifier un premier démarrage neuf et un reboot via la pipeline. La préparation native constatée ici doit être intégrée proprement à cette automatisation.
3. Sur cette version finale, vérifier l'import automatique S3, les cartes physiques QR/NFC, les trois connexions admin, la réception/validation email et la sauvegarde/restauration. La recharge TEST du témoin est validée ; la preuve finale Gala reste distincte.
4. Reprendre séparément les remboursements de recharges locales et les fonctions billetterie/adhésion. Le présent paiement TEST ne valide pas leur fonctionnement ni leur couverture juridique.
