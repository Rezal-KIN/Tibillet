# Nécessité des montages Docker — état vérifié le 8 octobre 2026

**Il faut conserver le stockage persistant. Les montages de fichiers Python et
HTML ne sont pas indispensables en tant que montages : certains portent une
fonction utile, d'autres une personnalisation facultative.** Les supprimer tous
sans distinguer ces usages casserait des fonctions de l'installation actuelle.

Cette analyse ne retire aucun montage, ne change aucun code applicatif, ne
déploie aucune release et ne modifie aucune base. Seuls ce document, son reçu
de preuves et des fichiers locaux de contrôle sont ajoutés. Les anciens audits
restent inchangés.

## Périmètre et références

- Dépôt local : `cc652f3f46bc6496ce9db9154405c59f1a3cdb4e`, branche
  `Vaporik/vaporik/remboursements-admin`.
- Instance active contrôlée : **Smoke**, `i-0037b98572fccdff2`, release au commit
  `d162e2647d7e36458a6c9be75fa1bc3248cb6e03`. Les Compose et les fichiers Python
  concernés sont identiques au dépôt local ; les empreintes des cinq Python
  chargés dans les conteneurs correspondent aux fichiers versionnés.
- Les autres instances, dont Aix et le nouveau gala de test arrêté, n'ont pas
  fait l'objet de cet inventaire runtime. Aucun redémarrage ni changement de
  routage n'a été réalisé pour cette analyse.
- Référence LaBoutik : `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`.
- Référence Fedow : `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c`.

Les sources exactes des images épinglées sont celles de
[`image-sources.json`](../../deploy/source/image-sources.json), avec archives
revérifiées par SHA-256. « Natif » désigne ces références, pas la dernière
branche amont. Le [reçu de preuves](2026-10-08-necessite-montages-preuves.json)
conserve les empreintes, comptages, commandes de contrôle et résultats utiles.

**41 montages ont été observés dans 15 conteneurs : 39 bind mounts déclarés
dans Compose et deux volumes Docker `/data` ajoutés par les images Redis.**
Les 39 bind mounts correspondent exactement aux déclarations. Un même dossier
peut être monté dans plusieurs conteneurs ; ce ne sont pas 41 fonctionnalités
ni 41 dossiers distincts.

## Matrice de nécessité

| Catégorie | Nombre de montages | Nécessité et conséquence d'un retrait | Recommandation |
| --- | ---: | --- | --- |
| Bases : Fedow SQLite, PostgreSQL natif Lespass et LaBoutik | 3 | Stockage durable indispensable si l'on veut conserver cartes, comptes, soldes et ventes lors d'une recréation des conteneurs. | Conserver hors des images. Changer le type de volume ne rendrait pas le code plus vanilla. |
| `www` : fichiers statiques et médias | 7 | Django produit les statiques et écrit les médias ; Nginx lit les mêmes dossiers. Retirer le partage actuel casse la desserte ou la conservation de ces fichiers. | Conserver pour le moment. Les médias doivent rester persistants ; les statiques pourraient être empaquetés séparément ultérieurement. |
| Logs Django, Gunicorn et Nginx | 7 | L'emplacement actuel est utilisé par les processus. La persistance sert au diagnostic après un déploiement ; elle n'est pas une fonctionnalité métier. | Conserver tant qu'aucune collecte de remplacement n'est configurée. |
| Certificats Traefik : `acme.json` | 1 | État et certificats HTTPS écrits pendant l'exécution. Le mettre dans une image figerait un état propre à l'instance. | Conserver persistant. |
| Socket Docker pour Traefik | 1 | Traefik utilise `providers.docker=true` et découvre les routes par les labels Docker. Sans socket, cette découverte ne fonctionne plus. | Conserver avec cette architecture ; il s'agit d'une communication avec Docker, pas d'une copie de code TiBillet. |
| Redis `/data` | 2 | Les deux Redis ont des snapshots périodiques configurés, sans AOF. Redis sert notamment à Celery et aux communications Channels ; effacer son état peut perdre des tâches en attente. | Conserver ; ne pas l'assimiler à un simple cache jetable. Les volumes observés ne prouvent pas à eux seuls la conservation de toutes les tâches entre releases. |
| Configuration Nginx | 3 | Porte les destinations Django/WebSocket, les statiques, les alias admin et `/source`. Supprimer les dossiers sans fournir cette configuration autrement casse le routage actuel. | La configuration est nécessaire, le bind mount ne l'est pas intrinsèquement. Une image Nginx versionnée pourrait l'embarquer, mais cela ajoute un build. |
| Publication `/source` | 3 | Sert l'index généré et l'accès aux sources correspondant à la release. Son retrait supprime cette publication locale. | Garder cette fonction ; un autre empaquetage est possible, sans nécessité de toucher au métier. |
| Fichiers Python | 5 | Remplacent cinq fichiers entiers des images. La nécessité dépend de la modification précise ; détails ci-dessous. | Réduire les modifications utiles, puis supprimer leur montage en les intégrant proprement aux images si elles restent nécessaires. |
| Templates HTML | 5 | Trois templates LaBoutik et un dossier admin partagé monté dans deux applications. Ajoutent des liens vers `/source/`, sans modification de paiement ou de carte. | Le montage n'est pas nécessaire. Garder l'accès visible aux sources par une adaptation minimale si l'on change leur empaquetage. |
| Dossiers SSH | 2 | Support prévu pour Borg par SSH. Les deux dossiers sont vides ; Borg n'est configuré dans aucun des deux conteneurs. Le backup S3 de l'hôte n'utilise pas ces dossiers. | Bons candidats au retrait dans la configuration actuelle. |
| `/Backup` | 2 | Lespass : aucun cron actif, aucun dump observé. LaBoutik : cron actif, trois tâches natives de sauvegarde, un dump présent. Borg n'est pas configuré, mais le dump local précède l'envoi Borg. | Lespass est un candidat au retrait. Pour LaBoutik, choisir explicitement de conserver ou de désactiver cette sauvegarde locale avant de retirer sa persistance. |

Les sauvegardes S3 sont indépendantes des deux dossiers `/Backup` et des clés
SSH : [`backup-postgres.sh`](../../deploy/tools/runtime/backup-postgres.sh)
lit les conteneurs PostgreSQL et le stockage SQLite, utilise un dossier
temporaire sur l'hôte, puis publie dans S3. Le timer de Smoke est actif. Ce
constat ne remplace pas un essai de restauration.

## Les cinq fichiers Python

### `deploy/Laboutik/views.py` et `validators.py`

La comparaison complète retrouve le code natif, sauf l'enregistrement d'une
carte inconnue et les messages d'erreur associés. Les écarts hérités de vente
de billets, d'adhésions et de sélection de carte examinés précédemment ont été
restaurés ; ils ne justifient plus ces montages.

La personnalisation enregistre dans Fedow une carte absente, uniquement après
une absence confirmée, puis exige une relecture réussie. **Elle est différente
de l'import automatique du stock au premier démarrage.**

Pour les 7 020 cartes de nos trois lots, l'import natif renseigne déjà le NFC,
le numéro imprimé et le QR avant utilisation. LaBoutik sait nativement
récupérer une carte connue de Fedow et la matérialiser localement. Nos sondes
sur les fonctions exactes, avec HTTP et ORM simulés, confirment que les deux
versions récupèrent une carte connue sans en créer une. Sur une carte inconnue,
seule notre version déclenche la création ; la version native la refuse.

**Ces deux modifications ne sont donc pas nécessaires pour utiliser les lots
déjà importés.** Elles restent nécessaires si l'on veut accepter automatiquement
des cartes qui n'appartiennent à aucun stock importé. L'utilisateur avait
précédemment choisi de garder cette fonction ; cette analyse ne révoque pas
ce choix.

Limite concrète : le scan NFC seul ne fournit pas le numéro imprimé ni le QR
physique. La création de secours utilise le NFC comme numéro et génère un QR.
Un futur import usine peut donc trouver un conflit. Un tel cas a déjà été
inspecté puis corrigé pour G1, sans remplacement automatique des associations :
voir l'[audit de l'import](2026-10-06-import-cartes-usine.md#conflit-examiné-et-correction-limitée-aux-identifiants-imprimés).

Recommandation pour rester proche du natif : si toutes les cartes utilisées
proviennent d'un catalogue importé, revenir aux deux fichiers natifs exacts
est plus simple que conserver la création de secours. Si l'on garde cette
dernière, intégrer seulement ses petits écarts dans une image LaBoutik fondée
sur la référence exacte, avec comparaison complète au build.

### `deploy/Laboutik/install.py`

Les écarts permettent de reprendre une première installation partielle :
réutilisation des appairages Lespass/Fedow déjà enregistrés, refus de changer
silencieusement leur destination, et réutilisation de l'admin existant sans
nouvelle invitation systématique.

Nuance essentielle : **l'installateur natif sort déjà lorsqu'un point de vente
existe.** La personnalisation ne justifie donc pas une nouvelle logique à
chaque mise à jour d'une installation complète. Son intérêt principal est
l'échec situé après l'appairage et avant la création des points de vente.

La pipeline relance l'installation LaBoutik après l'initialisation Lespass.
Dans une reprise partielle, l'endpoint Lespass à usage unique peut déjà être
consommé. Les fonctions natives exactes ne réutilisent pas l'appairage
persisté ; notre sonde simulée les voit recommencer leurs requêtes, tandis
que les fonctions actuelles réutilisent l'état local sans requête. Cette
sonde ne relance pas une installation réelle et ne prouve pas tous les
scénarios d'interruption.

**La reprise fiable est utile à la pipeline actuelle ; le montage du fichier
entier ne l'est pas.** Je recommande de garder provisoirement cette correction
ciblée. Un retrait doit être accompagné d'un bootstrap natif qui gère
correctement ce cas ; inventer un second installateur serait plus complexe.

### `deploy/Laboutik/settings.py`

Trois groupes d'écarts : chemin des templates admin de sources, backend email
configurable, et conversion des drapeaux TLS/SSL en booléens.

La pipeline fournit `EMAIL_USE_TLS='1'` et `EMAIL_USE_SSL='0'`. Les réglages
natifs utilisent directement les chaînes : `'0'` reste vrai en Python. Avec
ces valeurs, le constructeur SMTP de la version Django effectivement
installée lève `ValueError`, car TLS et SSL sont simultanément actifs.
Le constructeur accepte les booléens de notre configuration. Aucun test de
ce constat n'ouvre de connexion SMTP ni n'envoie de mail.

**Il faut corriger cette incompatibilité si l'on retire le fichier actuel.**
Cela n'impose cependant pas de modifier le code natif : un second essai du
constructeur confirme que conserver TLS non vide et fournir une chaîne vide
pour SSL convient à son fonctionnement natif. C'est une piste plus petite côté
configuration de la pipeline ; l'envoi réel et les modes d'environnement
resteraient à vérifier avant de l'appliquer.

Le backend configurable a un autre rôle : Smoke utilise actuellement
`django.core.mail.backends.dummy.EmailBackend`, qui absorbe les emails. Le
fichier natif ne lit pas cette variable. Corriger uniquement les drapeaux puis
revenir au natif ferait disparaître cette isolation des emails de test. Le
chemin des templates est aussi nécessaire au lien admin personnalisé actuel.

Recommandation : préserver le fonctionnement email et Smoke ; réduire le
réglage retenu à quelques lignes explicites dans l'image plutôt que monter
une copie complète. La piste du drapeau SSL vide évite potentiellement la
modification de conversion pour la production ; elle ne règle pas à elle
seule le backend de Smoke.

### `deploy/Fedow/settings.py`

Le bloc `DATABASES` est exactement le SQLite natif. **Ce montage n'est pas
nécessaire au retour à SQLite.** Il ne contient plus de bascule PostgreSQL.

Les écarts sont le chemin des templates de sources, les hôtes/origines de
sous-domaines ajoutés seulement en DEBUG, et le browser reload activé en DEBUG.
Les processus web actuels utilisent DEBUG faux. Le domaine public principal
figure dans les hôtes natifs ; ces écarts DEBUG ne sont pas nécessaires au
gala actuel.

Le besoin restant du fichier personnalisé est surtout le chargement du lien
admin vers les sources. Retirer les réglages actuels rendrait ce template
personnalisé non sélectionné. La publication Nginx `/source/` et son en-tête
HTTP restent indépendants ; ce constat ne décide pas de l'équivalence des
moyens d'accès aux sources.

Recommandation : candidat fort au retour aux réglages natifs exacts, en
prévoyant explicitement comment garder le lien de sources choisi. Si ce lien
est conservé de la même manière, seul un ajout minimal du chemin de templates
dans l'image est utile ; les écarts DEBUG peuvent être abandonnés.

## Présentation, configuration et données

Les trois templates HTML LaBoutik ajoutent uniquement des liens vers les
sources, à une variation d'espacement près. Le template admin partagé hérite
du template original et ajoute le même lien. Leur montage n'est nécessaire
ni aux recharges ni aux cartes. Une intégration aux images peut conserver
leur fonction sans modifier le métier.

Le dossier `www` demande une distinction : les médias sont des données
modifiables pendant un gala, les statiques sont générés par `collectstatic`.
Les deux anciennes copies CSS/JS sous `deploy/Lespass/www/static/` ne deviennent
pas fiables parce qu'elles se trouvent dans un volume : la collecte peut les
écraser. Les personnalisations que l'on veut garantir doivent être dans les
sources de l'image. Cela ne justifie pas de retirer tout `www` ; cette analyse
n'effectue aucune migration de présentation.

Les fonctions QR et web Lespass sont déjà intégrées à l'image construite du
dépôt. L'import automatique utilise la commande Fedow native inchangée avec
des fichiers temporaires ; **il n'ajoute pas de montage CSV ou de catalogue**.
Sa preuve sur un gala neuf est conservée dans
l'[audit de premier démarrage](2026-10-06-import-cartes-usine.md#résultats-du-premier-démarrage).

## Ordre proposé pour une simplification ultérieure

1. Conserver les bases, les médias, les certificats, Redis et le routage actuel.
2. Retirer en premier les montages manifestement superflus : les deux dossiers
   SSH vides, puis le `/Backup` Lespass après vérification de la cible à modifier.
3. Choisir si les cartes hors catalogue doivent encore être créées au scan.
   Si non, reprendre les deux fichiers LaBoutik natifs exacts et supprimer
   leurs montages, en conservant l'import automatique des stocks.
4. Garder la reprise d'installation et l'isolation email de Smoke ; intégrer
   seulement les écarts nécessaires dans des images épinglées construites
   depuis les références TiBillet vérifiées. Simplifier TLS/SSL côté configuration
   si les essais d'envoi et d'environnement le confirment.
5. Restaurer les écarts Fedow sans utilité actuelle et intégrer les liens de
   sources retenus sans montage de fichiers Python/HTML.
6. Refaire le test de premier démarrage, de relance, d'import, de QR et de
   parcours cashless après ces changements. Les sondes de cet audit ne valent
   pas une validation de ce futur état.

Mettre une ancienne copie entière dans une image élimine un bind mount mais
**ne réduit pas les écarts avec TiBillet**. Le critère utile est de partir du
code natif exact, de connaître chaque modification conservée, et de bloquer
un build si l'application d'une petite modification ne correspond plus à
la nouvelle référence.

Docker explique qu'un [bind mount masque le contenu de l'image à sa destination](https://docs.docker.com/engine/storage/bind-mounts/)
et qu'un [volume découple le stockage du cycle de vie du conteneur](https://docs.docker.com/engine/storage/volumes/).
Ces propriétés expliquent pourquoi le retrait des remplacements de code et
la conservation du stockage des données sont deux décisions différentes.

## Précisions demandées : intégration aux images et rôle des tâches

### Import des lots et création au scan

L'automatisation d'import peut être intégrée au code source de Fedow puis à
notre image. Une petite commande Django dédiée pourrait réutiliser
`import_stock` et la commande native `import_cards` inchangée. La pipeline
continuerait à récupérer les lots privés vérifiés et à appeler cette commande
après l'appairage du nouveau gala. Le code serait dans l'image, les identités
physiques resteraient des données de déploiement. Construire l'image ne
remplit pas la base d'un futur gala : l'exécution de l'import reste une étape
du premier démarrage.

Ce déplacement ne demande pas de conserver les personnalisations de
`views.py`/`validators.py` qui créent des cartes inconnues. Il s'agit de deux
fonctions différentes. Le choix de retirer la création au scan reste à faire.

### Installateur, emails, lien Fedow et templates

L'installateur reprenable, les quelques réglages email et les templates de
sources peuvent être inclus dans les images LaBoutik/Fedow. Cela demande
d'ajouter leur construction et leur publication à la pipeline actuelle,
qui utilise aujourd'hui les images de référence de ces deux applications.
L'intégration doit partir des sources exactes contrôlées, avec seulement
les modifications explicitement retenues.

Le défaut SMTP vient de la lecture de chaînes : TLS vaut `'1'`, SSL vaut
`'0'`, mais ces deux textes non vides sont vrais en Python. Le code natif
transmet donc simultanément deux modes de chiffrement incompatibles à Django.
La petite conversion explicite actuellement utilisée évite cela ; le backend
email configurable permet aussi d'absorber les messages de Smoke.

Le montage Fedow remplace tout le fichier `settings.py`, même lorsque l'ajout
utile concerne seulement le chemin des templates. Il ne remplace ni les
serializers de transactions ni le dashboard natif. Le bloc SQLite est
identique à la référence. Ses seuls autres écarts observés concernent les
hôtes/origines et le browser reload en DEBUG. Le risque de maintenance est
qu'une future correction des réglages de l'image amont reste masquée par
notre copie ; aucune altération du calcul des soldes n'a été identifiée dans
ce diff. L'ajout minimal du chemin de templates peut être intégré à l'image.

### Nginx et page de sources

Les fichiers Nginx peuvent être copiés dans `/etc/nginx/conf.d` au build,
au lieu d'y être montés depuis l'hôte. La page de sources peut aussi être
empaquetée, à condition de correspondre à la release réellement déployée.
Il faut conserver le partage des médias et des statiques avec Django.
Cette migration d'empaquetage ne change pas intentionnellement le routage,
mais un mauvais fichier ou chemin peut casser les pages, statiques, accès
admin ou WebSocket. Les contrôles à prévoir sont la validation Nginx et
les mêmes parcours sur une nouvelle instance.

### Exemples précis de travaux passant par Redis

Ce sont des types de tâches présents dans le code ; cette lecture ne mesure
pas le contenu des files en attente à l'instant de l'analyse.

| Travail | Preuve dans les sources |
| --- | --- |
| Envoyer l'email de connexion, notamment depuis le parcours QR | `AuthBillet/utils.py` appelle `connexion_celery_mailer.delay` après le commit ; tâche définie dans `BaseBillet/tasks.py`. |
| Transmettre une vente Lespass à LaBoutik, avec reprise après erreur | `send_sale_to_laboutik` dans `BaseBillet/tasks.py`, appelée via `.delay` dans les vues/signaux. |
| Envoyer billets, reçus ou notifications, selon la fonction utilisée | `ticket_celery_mailer`, `send_payment_success_user`, `send_membership_invoice_to_email` dans `BaseBillet/tasks.py`. |
| Produire et envoyer les rapports de caisse | `GetOrCreateRapportFromDate` et `envoie_rapport_et_ticketz_par_mail` dans `APIcashless/tasks.py` de LaBoutik native. |
| Imprimer les commandes et tickets lorsque le matériel est configuré | Tâches de `epsonprinter/tasks.py` de LaBoutik native. |

### SSH et sauvegardes

Les dossiers SSH servent à stocker les clés/paramètres d'une sauvegarde Borg
vers un serveur distant par SSH. Ils ne correspondent ni au lecteur NFC ni
à la connexion AWS de l'opérateur. Les deux dossiers étaient vides lors du
contrôle runtime de cet audit. Ils ne sont pas utilisés par les sauvegardes S3.

Le cron de LaBoutik lance trois fois par jour le script natif qui crée un
dump local dans `/Backup/dumps`, puis tente son transfert Borg. Le répertoire
monté est le stockage des résultats ; le programme de sauvegarde est déjà
dans le code de l'image. Modifier ce programme ne remplace donc pas, à lui
seul, le besoin de stocker un backup.

Pour utiliser exclusivement le mécanisme S3 déjà présent, la modification
la plus limitée serait de désactiver les seules entrées cron de sauvegarde
Borg dans notre construction LaBoutik, puis de retirer les montages SSH et
les `/Backup` devenus inutiles. Les autres tâches Celery resteraient intactes.
La sauvegarde de l'hôte n'a pas besoin de ces dossiers. Ce changement doit
être validé par une sauvegarde suivie d'une restauration, avant de considérer
le mécanisme remplacé. Il reste une proposition, pas un changement appliqué.
