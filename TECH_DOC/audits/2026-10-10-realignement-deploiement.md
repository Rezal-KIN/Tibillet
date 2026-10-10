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

La suite de déploiement a exécuté 137 tests avec succès, dont 3 ignorés.
Le scénario de régression refuse maintenant un worker répondant au broker mais
incapable de joindre Fedow. Les trois Compose fusionnés ont été contrôlés, ainsi
que la syntaxe shell et l'absence de montages applicatifs supplémentaires.

La livraison AWS et les vérifications sur une EC2 neuve sont une étape distincte.
Les résultats et limites réels seront ajoutés après les exécutions de pipeline,
sans présenter ces contrôles locaux comme une preuve du premier démarrage.
