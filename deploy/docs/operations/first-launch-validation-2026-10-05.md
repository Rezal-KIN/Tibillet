# Vérification d'un premier lancement — 5 octobre 2026

Objectif : créer une EC2 vide par Foundation, puis livrer exactement les images
validées par la pipeline Test. Les remboursements locaux restent hors périmètre.
Le gala Aix conserve son instance et son IP publique pendant cet essai.

## Corrections préparées avant l'essai

- Configuration du compte admin commun intégrée au déploiement avec le script
  existant, après les installateurs natifs. Les comptes, emails et relations
  sont préservés. L'empreinte vient de la version `GALA_ADMIN` du secret mail ;
  sa version `AWSCURRENT` reste identique pour les anciennes releases.
- CSS et JavaScript personnalisés existants copiés dans les sources statiques
  Lespass. `collectstatic` peut ainsi les reconstruire sur un disque vide.
- Logo et police manquants ajoutés aux mêmes sources, avec provenance et licence.
- Aucun modèle, migration ou traitement financier TiBillet modifié pour l'essai.

## Vérifications locales

107 tests de déploiement et 5 tests de politique réussis. La vérification des
fichiers restaurés confirme les sept unités natives et les seuls écarts
conservés dans LaBoutik. Une sonde Django/SQLite vérifie la configuration admin
et son idempotence. Une régression utilise aussi une vraie authentification
Django qui recalcule le hash ; la disponibilité des comptes survit à cette
modification native, tandis qu'un mot de passe inutilisable est refusé.
Un `collectstatic` isolé conserve les octets CSS, JS, logo et police.

## Contrôles réels à consigner

| Contrôle | Preuve attendue | État au début de l'essai |
| --- | --- | --- |
| Foundation | Exécution réussie, EC2 nouvelle, SSM et cloud-init terminés | À lancer |
| Test | SHA/digests identiques, déploiement SSM et marqueur S3 de réussite | À lancer |
| Production du nouveau gala | Artefact approuvé, même SHA/digests, SSM réussi | À lancer |
| Stockage natif | Fedow SQLite initialisé ; Lespass/LaBoutik PostgreSQL natifs | À vérifier |
| Appariement | Lespass et LaBoutik reliés au Fedow de cette EC2 | À vérifier |
| Administrations | Connexion correcte, refus d'un mauvais mot de passe | À vérifier |
| Site | HTTP, CSS/JS, logo/police, parcours personnalisés | À vérifier |
| QR et carte | Enregistrement automatique, liaison au compte, recharge test | À vérifier sur Smoke |
| Sauvegarde | Envoi S3 et restauration dans des bases isolées | À vérifier |
| Redémarrage | Services et accès opérationnels sans réparation | À vérifier |

Un succès HTTP ou un Checkout Stripe créé n'est pas une preuve de paiement,
de crédit de portefeuille, de remboursement ni de livraison d'un email.
Ces limites doivent rester explicites dans le résultat final.

Les IDs d'exécution, logs et reçus non sensibles de l'essai sont conservés dans
`.context/first-boot/`. Toute correction d'un échec applicatif doit être
versionnée puis rejouée par la pipeline, sans réparation du code sur l'EC2.

## Première tentative et correction

Foundation `fbebfaf3-1331-4244-90d5-f5eb0c193fb5` : réussie, commit
`3d1477b419edf3d784ba889da4a6c17d36684a96`. EC2 neuve
`i-00cb72994b875e92d`, SSM Online, cloud-init terminé et mêmes sources.
Le groupe réseau du nouveau gala n'a aucune entrée publique. Aix et Smoke
n'ont pas été remplacées. La pipeline Production créée cible cette EC2.

Test `bbe96e32-004f-4df6-9d0c-6fcba22469c3` : image construite, puis
déploiement SSM `149afb9f-791e-4f1f-97f0-e035003094df` annulé par l'agent
après diagnostic d'un contrôle admin incorrect. Les connexions HTTP des
trois administrations fonctionnaient, ainsi que les quatre assets exacts,
mais ces connexions déclenchaient la réécriture standard du hash par Django.
Le contrôle exigeait à tort des octets identiques au hash initial.
La correction vérifie un compte activé, privilégié et un mot de passe
utilisable reconnu par Django ; le déploiement applique toujours le hash
commun. Elle ne change aucun backend d'authentification applicatif.

L'ancien Smoke PostgreSQL est conservé dans S3 (backup
`20261005T215906Z`) et sous
`/var/lib/tibillet-gala-archives/gala-smoke-before-native-20261005`.
Les données de cette première tentative sont archivées séparément avant
une nouvelle exécution sur des bases vides. Aucune réparation applicative
locale n'est utilisée pour faire réussir le test.

Deuxième Test `a6353411-c1a3-4919-a82d-b21a12bdb5ec` : `Succeeded`,
commit `3a215c66afa89f12d423feb72eacd7c23086c2bd`. SSM
`b8cf6247-6ff7-4729-9c7f-9c4d72c3f0f6` réussi sur des bases à nouveau vides.
Les trois connexions HTTP ont réussi pendant le healthcheck, sans empêcher
sa validation. Les mots de passe incorrects sont refusés. Les quatre assets
servis ont les octets attendus ; l'accueil et l'offre de sources répondent 200.
Le marqueur immuable S3 `test-validated/smoke-3a215c66afa89f12d423feb72eacd7c23086c2bd.json`
correspond au commit et aux quatre digests du manifeste préparé.
