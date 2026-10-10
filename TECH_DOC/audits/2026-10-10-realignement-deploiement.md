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
- Le transport interne Lespass → Fedow reste provisoirement conservé. Son retrait
  exige la preuve du HTTPS natif sur une instance neuve inactive.
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

La livraison AWS et les vérifications sur une EC2 neuve sont une étape distincte.
Les résultats et limites réels seront ajoutés après les exécutions de pipeline,
sans présenter ces contrôles locaux comme une preuve du premier démarrage.


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
