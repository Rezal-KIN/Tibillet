# Différences restantes avec l'installation manuelle officielle — état du 10 octobre 2026

Comparaison après réalignement, avec le témoin réellement installé à la main les
9 et 10 octobre, puis supprimé. Guide :
[TiBillet/documentation_v2, server_install.md](https://github.com/TiBillet/documentation_v2/blob/1dc42966228e535a1a5a4f4a7a373323b6234a7c/docs/install/server_install.md).
Les fichiers extraits et leurs empreintes sont conservés dans les
[preuves de l'installation manuelle](2026-10-09-comparaison-installation-preuves.json).

Référence du dépôt final : `main@37ed3fc2a76c1c03da3d72f4058f122973539001`.
Les quatre images communes à Aix et Smoke proviennent du Test applicatif
`a3d9e82d40c76c2034a8e4eb238737b9aabb9eea`. La dernière fusion ne change
aucun code applicatif ni script runtime. La [preuve finale](2026-10-10-finalisation-preuves.json)
retrouve les mêmes images, montages et trois lots sur les deux hôtes.

Ce document est une synthèse actuelle ; les audits précédents restent historiques.
L'installation manuelle n'existe plus : sa comparaison utilise les inventaires
et reçus conservés, pas une nouvelle inspection d'une machine encore allumée.

## Code et interface actifs

| Différence restante | Forme | Utilisation et effet |
| --- | --- | --- |
| Parcours QR Gala | Code Python, routes et templates dans l'image Lespass | Inscription, liaison carte/portefeuille, connexion et preuve email selon l'état du compte et de la carte. TiBillet dispose déjà d'un parcours natif pour certaines cartes ; notre adaptation couvre le parcours Gala. |
| Extensions utilisateur pour ce parcours | `AuthBillet/utils.py`, vue QR, formulaire et email | Retour facultatif de l'état de création, template email QR, limitation des renvois, formulaire de liaison adapté. |
| Personnalisation et guide cashless | CSS, JS, images, police, templates Lespass | Apparence Gala et explications. Certains liens/libellés restent propres à Aix. |
| Menus masqués | CSS/JS Lespass | Agenda, adhésions, réservations, langue et thème masqués dans l'interface. Les fonctions serveur natives ne sont pas supprimées. Ce choix dépasse une modification de couleurs. |
| Enregistrement des cartes NFC inconnues sans QR | Deux fonctions Python LaBoutik : `check_carte`, `validate_tag_id` | Création/récupération de la carte après absence confirmée, appel du client Fedow natif et relecture. Pas de création sur simple erreur réseau. Ne reconstitue pas un numéro/QR déjà imprimé inconnu. |
| Connexion admin Lespass par mot de passe | `Administration/admin/site.py` | Active le formulaire Django en mode Gala, en conservant le parcours email. La redirection hors Gala vers `/?login=1` diffère aussi de l'origine. |
| Transport Lespass vers son Fedow local | `fedow_connect/fedow_api.py`, réseaux Docker | HTTP interne vers `fedow_nginx` en mode Gala, Host/signatures/délais natifs conservés ; HTTPS natif dans l'autre mode. Nécessaire à notre architecture avec plusieurs Galas partageant les domaines, avant certificat public. |
| Email configurable | Settings Lespass et LaBoutik | Conversion explicite TLS/SSL en booléens et choix du backend, notamment dummy sur Smoke. Le témoin natif pouvait fonctionner avec TLS actif et SSL vide sans patch. |
| Logs de connexion réduits | `BaseBillet/tasks.py` | Retire des logs le lien magique complet et l'URL de retour. |
| Installation LaBoutik reprenable | Une fonction de l'installateur dans l'image | Reprend les appairages et comptes déjà créés, limite les réinvitations au déploiement ; refuse le déplacement silencieux d'un appairage. |
| Liens vers les sources | Templates/settings des trois applications, liens admin et communautaires | Accès au code correspondant à la release ; Fedow ne garde que le chemin de template et le lien admin personnalisé. |

Les images Fedow/LaBoutik sont encore **dérivées**, pas strictement natives :
Fedow reçoit deux fichiers par `COPY`, LaBoutik huit. Cela représente neuf sources
uniques, le template admin étant utilisé deux fois. Des fichiers entiers sont
copiés, bien que leurs différences soient limitées et contrôlées. Une mise à jour
de leur image native demande donc une nouvelle comparaison de ces fichiers.

## Configuration appliquée et assemblage

| Différence restante | Forme | Utilisation et effet |
| --- | --- | --- |
| Tenant événement sur le domaine racine | Commande Lespass `configure_gala_apex.py` | Configure les modèles natifs Client/Domain pour les liens et QR imprimés ; le témoin utilise un domaine/sous-domaine propre à son installation. |
| Bouton recharge | Commande `configure_gala_refill.py` | Active le champ natif `force_show_refill_button` quand la configuration le permet ; ne réécrit pas le paiement. |
| Retour Stripe canonique | Script hôte `configure-gala-refill-domain.py` | Réconcilie le champ natif `Place.lespass_domain` après déplacement du tenant. Corrige notre ancien retour vers une page inexistante. |
| Clés Stripe et webhook | Script hôte `reconcile-fedow-webhook.py`, secrets runtime | Réconcilie les champs natifs ; traitement financier natif conservé. |
| Compte admin commun | Script hôte `configure-gala-admin.py` | Configure identifiant, hash et droits dans les trois applications à partir du secret privé. |
| Import automatique CSV/S3 | Scripts hôte et appel de `import_cards` natif Fedow | Dépôt S3, validation, catalogue figé par Test, import des absentes lors de livraison, contrôle sans doublon. Ni CSV monté, ni nouvelle commande d'import persistante dans Fedow. Un dépôt S3 seul ne modifie pas une instance active ; retirer un CSV n'efface pas ses cartes. |
| Paramètres propres à chaque Gala | Secrets Manager et fichiers runtime privés | Domaines, noms, timezone, email, Stripe, clés et appairages. Smoke TEST avec email dummy ; Aix LIVE inactif. Les données et clés ne doivent pas être identiques entre eux. |
| Variables PostgreSQL résiduelles Fedow | Rendu d'environnement | `POSTGRES_DB/USER/PASSWORD` sont encore générées mais n'activent pas PostgreSQL : le bloc Fedow utilise SQLite natif. |
| Routage des domaines publics | Labels Traefik/Compose | Lespass expose le domaine principal ; les alias `www`, `festival`, `agenda`, `m` ne sont pas tous exposés/DNS configurés comme dans une installation dédiée. |
| Résolution des applications locales | Réseaux, `extra_hosts: host-gateway` | Web et worker contactent leurs pairs sur la même EC2, malgré des noms publics partagés ; maintient la vérification TLS normale pour les appels HTTPS natifs. |
| Contenu des trois Nginx | Configuration montée | `/source/` et header Link dans les trois ; alias admin dans Lespass/LaBoutik ; resolver Docker et upstream dynamique dans Lespass. Fedow reprend sinon l'extrait exact du guide. Ports, médias et réglages WebSocket natifs sont conservés. |
| Construction et choix des images | Dockerfiles, ECR, manifestes à digests | Images du fork/dérivées et promotion des images exactement testées, au lieu des images TiBillet `latest` du guide. Les services auxiliaires ne sont pas tous fixés au digest. |
| Système de base Lespass | Dockerfile | Python 3.11 Bookworm au lieu de Bullseye ; installation APT regroupée. `pyproject.toml` et `poetry.lock` inchangés. |
| Version amont Lespass | Origine du fork contre image native du témoin | Treize fichiers du témoin diffèrent à cause de la version amont ; dix fichiers de documentation/IDE/tests sont absents de notre image. Ce ne sont pas des suppressions de fonctionnalités réalisées par nous. Détail dans le TSV de comparaison des images. |

## Exploitation ajoutée par notre projet

| Ensemble | Forme | Rôle |
| --- | --- | --- |
| Infrastructure AWS | Terraform, EC2/EBS, IAM/SSM, security groups, ressources de stockage | Création des Galas, accès opérateur, protections et gestion du cycle de vie. Le guide ne prescrit pas cette infrastructure. |
| Pipelines Foundation/Test/Production | CodePipeline, CodeBuild, scripts, plans et approbations | Construction, installation neuve, validation et livraison d'un manifeste exact. |
| Choix du Gala public | Pipeline de bascule, EIP, marqueur SSM | Un seul Gala reçoit le trafic des domaines partagés. Le témoin manuel avait son propre domaine. |
| Démarrage et reprise | systemd, scripts hôte | Migrations/installateurs natifs, réglages, démarrage au reboot avec images figées, reprise d'une livraison interrompue, rechargement des Nginx réutilisés. |
| Contrôles de livraison | Scripts hôte et garde-fous | Images/sources, cible, espace libre, backup, appairage, worker, domaines/admin/recharge et contrôle des stocks ; peuvent bloquer une livraison. |
| Sauvegarde/restauration S3 | Timer toutes les six heures, dumps PostgreSQL, snapshot SQLite, scripts de restauration | Supplément aux sauvegardes natives ; archives des bases anciennes conservées séparément. Les montages SSH/Borg restent mais notre S3 ne les utilise pas. |
| Publication et provenance des sources | Archives GitHub, pages `/source`, notices/labels/empreintes | Offre du code correspondant aux images livrées et contrôle de ses écarts. |
| Ressources et coûts | Swap 2 Gio/swappiness 10, nettoyage d'images inutilisées, politiques/budget/rétention | Le témoin avait 4 Go de swap. Le nettoyage ne retire pas les bases applicatives. |
| Documentation/tests/archives/développement | Fichiers Git ; tests/sondes/outils opérateur | Preuves, fonctionnalités retirées, manifestes historiques, exemples, outils historiques et gitlink de développement. Hors serveur financier ; certains fichiers annexes restent embarqués dans l'image Lespass par la copie du dépôt. |

Le dépôt reste spécifique au compte AWS, région et domaines Gala configurés.
Ce n'est pas un installateur générique sans paramètres propres au projet.

## Montages : comptage exact après livraison

Comptage par conteneur/destination : **31 chez nous, 26 dans le témoin manuel**.

| Groupe | Chez nous | Origine |
| --- | ---: | --- |
| Bases persistantes | 3 | Guide officiel ; dossier hôte SQLite nommé différemment chez nous |
| Médias/statiques Django et Nginx | 6 | Guide officiel |
| Logs Django et Nginx | 6 | Guide officiel |
| Configuration Nginx | 3 | Guide officiel ; contenu adapté ci-dessus |
| Sauvegardes `/Backup` | 2 | Guide officiel |
| SSH/Borg | 2 | Guide officiel, optionnel |
| Redis `/data` | 2 | Volumes implicitement créés par les images natives |
| Socket Docker + `acme.json` Traefik | 2 | Reverse proxy requis par le guide ; mêmes types dans le témoin manuel |
| Sources `/source`, lecture seule | 3 | Ajout de notre projet |
| `www` du worker Celery | 1 | Ajout de notre projet : médias partagés |
| `logs` du worker Celery | 1 | Ajout de notre projet : dossier/logs persistants ; absence du dossier faisait redémarrer le worker natif |

Donc **cinq montages supplémentaires** au témoin : trois `/source` et deux Celery.
Leurs données ne remplacent pas le code Python/HTML de Django.
Les deux montages Traefik ne sont pas fournis dans les trois Compose du guide,
mais existent aussi dans le témoin car le guide exige un reverse proxy.
Aucun montage Python/HTML/CSV applicatif n'est présent sur Aix ou Smoke inspectés.

## Retour au natif déjà effectué

- Fedow SQLite ; Lespass PostgreSQL 13 ; LaBoutik PostgreSQL 11.5 : mêmes moteurs
  et versions de bases que le guide, pas une migration générale vers PostgreSQL.
- Calcul des soldes, transactions/recharge, remboursement natif, modèles et
  migrations Lespass, serializer/dashboard/importeur Fedow : sources natives.
- Anciennes variantes LaBoutik billets, adhésions, choix de carte responsable,
  erreurs et doublons : restaurées ; restent seulement les exceptions NFC décrites.
- Monnaie cadeau : synchronisation native, toggle ajouté retiré.
- Dashboard financier personnalisé, happy hour et limite de terminaux : retirés.
- Restart LaBoutik : `always` natif rétabli. Commandes Celery, memcached,
  absence de worker séparé LaBoutik et volumes de données : ceux du guide serveur.
- Ancien remboursement local IBAN/BIC 100J : archive V1, pas une fonction active V2.

Ces égalités portent sur les sources comparées. Elles ne constituent pas une
validation exhaustive de tous les scénarios de paiement/remboursement/adhésion.

## Annexes et précision sur les nombres

- [Tous les chemins du dépôt final comparés à l'origine du fork](2026-10-10-differences-installation-officielle-fichiers.tsv) :
  **370 chemins avant ajout de ce présent audit, 353 ajoutés et 17 modifiés**.
  Documentation, infrastructure, tests et archives comptent dans ce nombre ;
  il ne représente pas 370 modifications métier.
- [Comparaison des fichiers des images natives et personnalisées](2026-10-09-comparaison-images-fichiers.tsv) :
  détails de personnalisation et de version du témoin. Les déploiements suivants
  n'ont pas ajouté de patch applicatif depuis ce relevé ; leurs fichiers annexes
  de livraison/documentation ont évolué.
- [Montages et lignes du guide](2026-10-09-montages-guide-officiel.tsv).
- [Défauts corrigés et premier lancement/reboot neuf](2026-10-10-realignement-deploiement.md).
- [Recette et livraison Aix finale](2026-10-10-finalisation-main-et-retrait.md).

Ce document n'implique aucune nouvelle modification de l'application, livraison
AWS, import de carte ou bascule publique.
