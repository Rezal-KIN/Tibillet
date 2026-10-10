# Réalignement du déploiement — 10 octobre 2026

Suite autorisée de l'[audit de comparaison](2026-10-09-comparaison-installation-officielle.md)
et de l'[investigation du routage](2026-10-09-domaine-racine-et-nginx.md).
Les audits du 9 octobre décrivent l'état avant ces corrections et restent conservés.

## Changements de configuration

| Point | Correction | Origine |
| --- | --- | --- |
| Worker Lespass → Fedow | Rattachement de Celery au réseau Docker `frontend` déjà utilisé par le serveur web et Fedow | Répare notre adaptation au transport interne |
| Lespass → LaBoutik | Résolution du domaine cashless par `host-gateway` dans web et worker | Complète notre configuration des Galas partageant les domaines publics |
| Fedow → Lespass | Résolution locale du domaine canonique dans la superposition de release | Le callback d'adhésion natif reste inchangé, avec vérification TLS normale |
| Redémarrage LaBoutik | Retour à `restart: always` pour ses cinq services | Valeur du guide officiel TiBillet |
| Nginx Fedow | Reprise du fichier exact extrait du guide, puis réintroduction des seuls blocs `/source/` et du header de source | Restaure `/media`, logs, `X-Real-IP` et upstream natifs |
| Noms Nginx | Retour au `server_name localhost` des trois extraits officiels | Le Host transmis et les règles Traefik déterminent toujours les domaines publics |
| Contrôle de santé | Vérifie Fedow depuis web ET Celery, puis les correspondances locales des pairs | Empêche une validation web/broker de masquer le défaut réseau constaté |
| Démarrage systemd | Après release saine et sauvegardée, réconcilie l'unité de boot ; redémarrage avec `--no-build` | Résout l'état historique de premier démarrage et conserve les digests livrés |
| Rechargement Nginx | Vérifie la syntaxe puis recharge les proxies réutilisés après mise à jour de leur stack | Un fichier monté mis à jour ne provoque pas à lui seul une relecture du processus ; reprend aussi la résolution des backends recréés |

Aucun modèle, migration, calcul de solde ou fonction de paiement n'est modifié.
Aucun montage de code ou de CSV n'est ajouté. Les commandes natives de migrations
et d'installation restent appelées par la pipeline existante.

## Écarts conservés et limites

- Le tenant Gala conserve son domaine racine et les URLs QR imprimées.
- Le parcours QR, l'identité visuelle, l'enregistrement NFC, l'importeur natif raccordé
  à S3, les comptes admin et l'accès aux sources restent en place.
- Le transport interne Lespass → Fedow reste conservé : sur le gala neuf
  **inactif**, les sept appels HTTPS natifs échouent sur le certificat provisoire.
  Une résolution locale correcte ne suffit pas à rendre ce certificat fiable.
- Aucun changement des réglages SMTP ni retrait de montage Celery n'est appliqué
  sur une simple hypothèse. Le rôle de chaque montage reste documenté.
- Les domaines secondaires `www`, `festival`, `agenda`, `m` n'ont pas de DNS
  lors du contrôle du 10 octobre. Leur ouverture n'est pas ajoutée à la règle ACME
  du domaine principal : un SAN sans DNS ferait échouer l'émission du certificat.
  Ce choix d'exposition doit être explicite avant ajout de DNS et de routes.
- Un premier démarrage inactif peut avoir le certificat temporaire de Traefik.
  La résolution locale est nécessaire, mais ne suffit pas à établir sa confiance
  TLS ; les clients natifs gardent leur vérification normale.

## Vérification locale

La première suite de déploiement a exécuté 137 tests, dont 3 ignorés. Après le défaut de premier démarrage détecté sur AWS, 144 tests sont exécutés, dont 3 ignorés.
Le scénario de régression refuse maintenant un worker répondant au broker mais
incapable de joindre Fedow. Les trois Compose fusionnés ont été contrôlés, ainsi
que la syntaxe shell et l'absence de montages applicatifs supplémentaires.

La livraison AWS et les vérifications sur une EC2 neuve sont une étape distincte,
consignée ci-dessous. Les contrôles locaux seuls ne prouvent pas le premier démarrage.


## Première exécution AWS et correction de reprise

- Foundation `8808ae9c-056e-45ed-9c9c-f3c4630b234b` a réussi et créé
  `i-0fb1dd7f460d6d88d`, sans remplacer Smoke ni Aix.
- Test Smoke `4007cced-c46e-463b-b93b-e9b3f08672f6` a réussi au commit
  `8269c9d98738f5b90783a7d4f2c846661c616ae3`. Les appels HTTPS natifs entre
  les quatre clients applicatifs passent sur Smoke actif, sans désactiver TLS.
- Production d'essai `76c37ccf-99e9-4102-b910-62c8d90dd537` a validé le
  manifeste exact avant approbation, puis échoué au premier démarrage sur
  `Nginx configuration reload failed: fedow_nginx`. La syntaxe avait passé ;
  le rechargement immédiatement après création peut précéder l'écriture du PID.
- Correction hôte : enregistrer l'identité du proxy avant Compose et ne le
  recharger que si ce même conteneur est réutilisé. Un proxy neuf/recréé lit
  la configuration à son démarrage. Les erreurs de syntaxe et les erreurs de
  rechargement d'un proxy réutilisé restent bloquantes.
- La préparation SQLite écrit maintenant son marqueur `initializing` **avant**
  le premier démarrage natif, uniquement sur un stockage neuf validé. Un
  premier déploiement interrompu peut ainsi reprendre. Une base SQLite sans
  marqueur, des données PostgreSQL historiques ou une ancienne release restent
  refusées ; aucune base inconnue n'est adoptée ou effacée automatiquement.
- L'EC2 du premier essai est arrêtée et conservée pour analyse. La preuve finale
  doit provenir d'une seconde EC2 vierge, sans réparation manuelle du premier hôte.

Les identifiants, lots privés de cartes et valeurs de secrets restent hors du dépôt.


## Premier démarrage corrigé et archivage Aix

Le second essai est une EC2 **vierge**, `i-03a85efbda0291201`, créée par
Foundation `106a4cf8-a376-4218-a31f-997ce2cdbc81` (succès). Test Smoke
`cc69c084-ae14-4438-b558-24d0827807ae` a réussi pour le commit applicatif
`60147839fd529828b00948b1179e0fa4924ac3d1`. Production d'essai
`f2b122c4-6c98-4231-8e8d-17375b8c531b` a réussi sans réparation manuelle
sur l'hôte, après validation du manifeste et approbation de ses octets exacts.

Les contrôles sur cet hôte retrouvent Fedow **SQLite**, Lespass/LaBoutik
**PostgreSQL natifs**, un lieu Fedow appairé, le tenant Gala sur l'apex et trois
points de vente natifs. Les **7 020 cartes** sont présentes en trois générations
(3 510, 1 755, 1 755) ; une vérification supplémentaire par l'importeur constate
`created=0` et `existing=7020`. Un QR importé et le média Fedow répondent 200.
Le worker joint son Fedow local, les comptes admin sont configurés, le contrôle
de santé et l'unité de boot sont en succès. Aucun fichier Python/HTML/CSV n'est
monté sur les conteneurs applicatifs inspectés.

La sauvegarde initiale `20261010T120105Z` a été restaurée isolément : 59 tables
LaBoutik, 180 tables Lespass et intégrité/clés étrangères/configuration SQLite
Fedow vérifiées. Cette preuve structurelle ne constitue pas un paiement ni
une restauration applicative sur les données actives.

Le diagnostic HTTPS **avant activation** retourne `SSLError` pour les sept
appels des quatre clients natifs, tandis que leurs noms résolvent correctement
vers le gateway local. Cela confirme que le certificat provisoire d'une EC2
inactive empêche de retirer simplement notre transport interne Lespass/Fedow.
La vérification TLS normale des applications reste activée.

L'utilisateur a ensuite autorisé l'archivage des **trois bases historiques Aix**.
Le script ponctuel versionné a réussi sur la seule EC2 inactive
`i-0801aa8a2273838aa` (commande `86886be9-bcdd-468b-b8b5-6802369096ca`).
La sauvegarde `20261010T115551Z` a été restaurée dans des conteneurs isolés
(27 tables Fedow, 1 620 Lespass, 59 LaBoutik). Les anciens dossiers PostgreSQL
restent sous le dossier privé de données historiques de l'hôte. Les clés,
paramètres réels de conteneurs, données Redis et deux écarts de fichiers
statiques générés sont dans une archive S3 privée relue et comparée après
upload. Aucune base n'a été effacée. De nouveaux caches/files accompagneront
les bases neuves pour éviter de reprendre des tâches liées aux anciens UUID.

La release Aix `gala-am-aix-native-20261010-v2` fixe les mêmes trois images
applicatives, Traefik, commit et catalogue que le gala neuf et Smoke. Production
`5af0a284-973c-4da8-91ab-27942ddf4a73` a réussi ; la commande de livraison
`1f0cc0ae-07fa-44b4-9c5d-4cb170363136` est en succès. Les trois nouvelles bases
ont été installées et appairées par les commandes TiBillet natives.

Les contrôles Aix retrouvent SQLite Fedow, PostgreSQL Lespass/LaBoutik, un lieu,
trois points de vente, le tenant `festival` sur l'apex et 7 020 cartes. L'importeur
confirme `created=0`, `existing=7020` ; le QR importé et le média Fedow répondent
200. La sauvegarde neuve `20261010T121505Z` a été restaurée isolément
(59/180 tables PostgreSQL et intégrité SQLite vérifiée). Les certificats déjà
présents sur Aix permettent aux sept appels HTTPS natifs de passer même lorsque
cette instance est inactive. Le nouveau gala sans certificat prouve la limite
différente du premier démarrage.

## Redémarrage réel et exposition publique du gala neuf

Un redémarrage EC2 réel du gala neuf a changé son identifiant de boot. Après ce
redémarrage, la commande `7fb7b65e-39dc-4c7e-869e-b758f60e4bda` retrouve l'unité
systemd `active/exited`, `Result=success`, les services disponibles et les
7 020 cartes conservées. Les anciennes données n'ont pas été utilisées pour
préparer cet essai.

La bascule temporaire `71a95e4e-4f55-4043-8acc-18011f765824` a réussi après
revue puis approbation du plan exact. Les trois domaines publics répondent
200 avec vérification du certificat, sans option `--insecure`. Cette bascule
inclut le redémarrage versionné de Traefik après ouverture de l'accès public,
pour permettre l'émission ACME sur une instance auparavant inactive.

Les sept appels natifs depuis web Lespass, Celery, Fedow et LaBoutik répondent
également 200 avec vérification TLS après activation. La commande de contrôle
est `3f3a2ad4-33da-40ca-979f-c984de9961a0` (succès). Il s'agit d'appels de
connectivité ; ils ne constituent pas une recharge Stripe, une vente physique
ou une vérification exhaustive des callbacks financiers.

## Montages réellement conservés

L'inspection renouvelée des 15 conteneurs de chacun des trois hôtes retrouve
les mêmes images applicatives et Traefik, le même commit et les trois lots du
catalogue. Les clés, bases et valeurs propres à chaque gala restent distinctes.

| Montage | Origine et rôle | État après livraison |
| --- | --- | --- |
| Bases, `www`, logs, sauvegardes, SSH ; configuration Nginx | Prescrits par le guide TiBillet | Conservés ; les données ne remplacent aucun fichier Python/HTML de l'application |
| `/data` des deux Redis | Volumes déclarés par l'image Redis | Conservés pour les files et caches ; caches Aix neufs, anciens RDB archivés |
| `www` et logs Celery | Deux montages ajoutés par notre installation | Conservés ; média partagé et logs du worker, aucun fichier applicatif remplacé |
| `/source` dans les trois Nginx | Trois montages supplémentaires, en lecture seule | Offre publique de sources ; documents/archives statiques servis par Nginx, aucun code exécuté dans Django |
| `acme.json` et socket Docker Traefik | Mise en œuvre du proxy, absent du Compose du guide | Certificats persistants et découverte des routes ; mêmes types que le témoin manuel |
| Code applicatif ou CSV | Anciens montages personnalisés | Aucun retrouvé ; importer les cartes passe par le script hôte et la commande native dans l'image |

Cette inspection ne signifie donc pas « zéro volume » : **cinq montages
supplémentaires par rapport au témoin manuel restent présents**, les deux
Celery et les trois offres de sources. Leur origine reste explicitement
documentée dans l'[inventaire du guide](2026-10-09-montages-guide-officiel.tsv).

## Retour à Smoke, preuves et limites

La bascule retour `26276481-3e46-4782-b31e-408339eff21e` a réussi après revue et
approbation de son propre plan. L'EIP partagée et le paramètre `active-gala`
désignent de nouveau **Smoke**. Les trois domaines publics répondent 200 avec
certificat vérifié après ce retour. Aix est reconstruit, mais n'est pas le gala
qui reçoit actuellement le trafic public.

Le contrôle Smoke `c68c8ab4-6523-4b0d-a966-7a9a4623fe2e` passe également :
sept appels HTTPS natifs, santé du worker, unité systemd, moteurs de bases et
réimport sans doublon. Smoke conserve 7 023 cartes au total ; l'importeur
reconnaît les 7 020 cartes attendues du catalogue. Les trois cartes
supplémentaires n'ont pas été supprimées pour forcer une égalité avec les bases
vierges Aix et du gala neuf.

Les résultats assainis, commandes SSM, images et inspections de montages sont
regroupés dans les [preuves du réalignement](2026-10-10-realignement-preuves.json).
Les sorties complètes et configurations privées restent dans `.context` et
les sauvegardes privées ; ni secrets ni correspondances de cartes n'entrent
dans ce document ou le JSON publié.

Les deux EC2 d'essai sont arrêtées, avec leurs disques conservés. Le premier
essai garde le défaut observé ; le second garde la preuve du démarrage corrigé,
du reboot et de la bascule. Aucun de ces arrêts n'est une suppression Terraform.

Les offres de sources correspondant aux livraisons sont publiées :

- [Gala neuf](https://github.com/Rezal-KIN/Tibillet/releases/tag/sources-gala-alignement-final-2026-10-10-native-20261010-v1-60147839fd52).
- [Aix reconstruit](https://github.com/Rezal-KIN/Tibillet/releases/tag/sources-gala-am-aix-native-20261010-v2-60147839fd52).

**Ce qui reste à faire, par priorité :**

1. Intégrer la PR #106 à `main` pour que les futurs lancements standards
   reprennent ces corrections. Les livraisons vérifiées ici utilisent le commit
   exact approuvé ; elles ne constituent pas une fusion de la PR.
2. Compléter la recette utilisateur sur Smoke : recharge Stripe TEST, réception
   email selon le dispositif de test retenu, connexion admin saisie et vente/scan
   physique. Aucun paiement n'a été effectué pendant cette session ; les galas
   hors Smoke gardent leur configuration Stripe LIVE. Le backend email dummy
   Smoke n'envoie pas de message et le relais vers une boîte de test n'est pas
   implémenté. Les contrôles présents ne prouvent donc aucune réception email.
3. Décider du retrait ultérieur des ressources/disques d'essai conservés après
   exploitation des preuves. Ils sont arrêtés, mais leur stockage reste facturé.

Les restaurations ont vérifié les bases dans des conteneurs isolés, sans
remplacer les bases actives. Le reboot réel a été testé sur le gala neuf ; Aix
n'a pas été redémarré pour cette recette. Les noms secondaires sans DNS restent
hors des certificats ACME. Nginx Lespass émet 220 avertissements pendant son
contrôle ; sa syntaxe passe. Ils ne sont pas corrigés dans cette livraison,
ni comptés comme une validation de toutes ses routes.
