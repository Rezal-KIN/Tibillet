# Vérification d'un premier lancement — 5 et 6 octobre 2026

Objectif : créer une EC2 vide par Foundation, puis livrer exactement les images
validées par la pipeline Test. Les remboursements locaux restent hors périmètre.
Le gala Aix conserve son instance et son IP publique pendant cet essai.

**Résultat : Foundation, Test et Production réussies sur AWS.** Une nouvelle
instance a été créée, initialisée sans données préexistantes et redémarrée
sans réparation manuelle. Les accès admin, le site, les cartes, la lecture QR,
Celery, les sauvegardes et la restauration isolée ont été vérifiés. Un défaut
du contrôle admin a été corrigé et retesté avant la promotion. Les derniers
changements restent sur la branche, à intégrer dans `main` après revue.
Le premier déploiement SSM de la nouvelle instance a duré 9 min 44 s.


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

| Contrôle | Preuve attendue | Résultat |
| --- | --- | --- |
| Foundation | Exécution réussie, EC2 nouvelle, SSM et cloud-init terminés | Réussi |
| Test | SHA/digests identiques, déploiement SSM et marqueur S3 de réussite | Réussi après correction du contrôle admin |
| Production du nouveau gala | Artefact approuvé, même SHA/digests, SSM réussi | Réussi |
| Stockage natif | Fedow SQLite initialisé ; Lespass/LaBoutik PostgreSQL natifs | Vérifié, intégrité et clés étrangères SQLite valides |
| Appariement | Lespass et LaBoutik reliés au Fedow de cette EC2 | Vérifié par création de carte et lecture QR réelles |
| Administrations | Connexion correcte, refus d'un mauvais mot de passe | Vérifié pour les trois services et l'alias cashless `/admin` |
| Site | HTTP, CSS/JS, logo/police, parcours personnalisés | HTTP 200 ; les quatre assets ont les SHA256 attendus |
| QR et carte | Enregistrement automatique, liaison au compte, recharge test | Réussi sur Smoke, sans paiement |
| Sauvegarde | Envoi S3 et restauration dans des bases isolées | Réussi pour les deux PostgreSQL et Fedow SQLite |
| Redémarrage | Services et accès opérationnels sans réparation | Réussi : systemd, mêmes images, données et accès conservés |

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

## QR et enregistrement automatique sur Smoke

SSM `177403c5-1d36-48f8-8679-c2622ed817b4` : le parcours réel QR a réussi
(1 test), ainsi que les 4 contrôles d'appropriation de carte. Le premier scan
QR, la création du compte, la liaison à son portefeuille et la création d'un
Checkout Stripe test sont vérifiés. Aucun paiement ni email SMTP exécuté.
La commande globale échouait ensuite dans une sonde temporaire qui cherchait
`STRIPE_TEST` dans LaBoutik, où cette variable n'existe pas. Ce défaut de sonde
n'a nécessité aucune modification applicative.

La sonde d'enregistrement a ensuite contrôlé les modes test de Fedow/Lespass
et le backend mail dummy avant d'appeler LaBoutik. Une première invocation
`55e1e02d-ceca-4a00-ac60-de980a1b183c` a été arrêtée par son garde de slug
(la configuration shell contient une valeur citée). Le garde corrigé source
la configuration. SSM `8f44176c-8bbb-42ad-aa75-3e5f684c9453` : réussi.
Le POST réel `/wv/check_carte` crée la carte inconnue dans les deux applications ;
le deuxième scan conserve un seul enregistrement et le même UUID QR.
Le healthcheck complet et Celery restent opérationnels après ces essais.

## Promotion de la nouvelle instance

Exécution `1fb9ed8a-3e60-4dc7-8da6-61d6b527bfd9`, source du manifeste
`85a30e6f285d36e08dae4ec03dec491d4110f6a2`, commit applicatif testé
`3a215c66afa89f12d423feb72eacd7c23086c2bd`.
Validation CodeBuild `68249864-b545-4347-955d-f84d7250736e` réussie avant
l'approbation. L'artefact téléchargé est identique octet pour octet au manifeste
versionné ; ses quatre images correspondent au marqueur Smoke immuable.
SHA256 du manifeste :
`132fa28688da76358eb0a1218d26cb58ff391637cab04872e3f6e3fd361a24ce`.
La cible vérifiée et approuvée est uniquement `i-00cb72994b875e92d`.
Déploiement SSM `3749c31a-10c6-4012-9d8f-83d69b50fa3f` réussi ;
pipeline Production au statut final `Succeeded`.

Ces tests utilisent un commit explicite de la branche de travail. Aucune fusion
vers `main`, déplacement de l'IP publique ou modification du DNS n'est effectué.

Le bootstrap natif de LaBoutik a aussi émis une invitation d'administration
via SMTP (journal applicatif indiquant un envoi réussi). Cela ne vérifie pas
la réception dans la boîte destinataire ni le parcours de connexion par mail.
Les sondes QR sur Smoke utilisent toujours le backend dummy. Les journaux
bruts pouvant contenir des liens d'activation restent privés dans `.context` ;
ces liens ne sont pas reproduits dans cet audit.

## Contrôles après le premier déploiement

SSM `02aea804-c177-400d-9db6-dca8cab967c5` réussi : commit runtime identique
au commit applicatif, manifeste déployé avec le SHA256 approuvé, Fedow SQLite
natif et aucun conteneur Fedow PostgreSQL actif. Lespass et LaBoutik conservent
leurs moteurs PostgreSQL natifs. L'intégrité SQLite, ses clés étrangères et
sa configuration unique sont validées. Avant la sonde de carte, la base
Fedow ne contenait aucune carte. Le timer de sauvegarde est actif et une
première sauvegarde a été envoyée à S3 (`20261005T224401Z`).

SSM `1c0e7ee0-caaf-4b95-8567-e23a31bf83eb` réussi : scan d'une carte inconnue
puis second scan sans doublon sur la nouvelle instance, sans paiement.
Lespass affiche ensuite le formulaire QR de cette carte via le vrai Fedow.
Les trois administrations ont été testées en HTTP, avec refus d'un mauvais
mot de passe et ouverture du dashboard avec le bon. L'alias LaBoutik `/admin`
rejoint son administration native. L'accueil, les quatre assets et `/source/`
répondent 200 ; les assets ont les octets des sources versionnées.

Une première sonde HTTP a rencontré un timeout TLS du tunnel SSM après les
deux premiers services. La sonde suivante a réussi tous les contrôles ; elle
ne réessaie que l'établissement de connexion TLS, jamais un POST soumis ni
une assertion applicative. Ces contrôles utilisent le certificat temporaire
local : ils ne valident pas le TLS public, le rendu visuel dans un navigateur
ni une bascule d'IP.

## Sauvegarde et restauration réelle

SSM `c08502ee-2672-4ca1-aea2-7ca4473f7f09` réussi : sauvegarde
`20261005T224912Z` après création de la carte de test, envoyée au préfixe S3
du nouveau gala. Le drill télécharge et contrôle les checksums avant de
restaurer LaBoutik (59 tables) et Lespass (180 tables) dans des conteneurs
PostgreSQL temporaires, sans réseau ni volume hôte. La copie SQLite passe
`integrity_check`, `foreign_key_check` et les contrôles des tables natives.
Les bases de l'instance ne sont pas remplacées par le drill. Le healthcheck
complet reste valide ensuite.

## Redémarrage et état final

Reboot de la nouvelle EC2 demandé seulement après la restauration isolée
réussie et vérification que le gala actif reste `gala-am-aix`.
SSM `d2516eaa-8ab2-479a-9a0a-7dce0d5d7ac4` réussi : boot ID passé de
`32785689-6715-4aad-8a20-675b16dfd226` à
`f46c2e0a-6506-4739-81dc-904b5f0d4416`, unité systemd stacks active,
timer backup actif et services opérationnels. Fedow contient toujours la
carte de la sonde avec son UUID initial. Les accès HTTP, l'alias admin, le
formulaire QR et les quatre assets ont été vérifiés à nouveau après reboot.
Aucun script de réparation ni redémarrage manuel de service n'est utilisé.

SSM `963aca39-1828-4e52-82f7-88de80ef4be5` réussi : les images des trois
applications, de Celery et de Traefik sont les digests approuvés. Le compteur
de redémarrages des cinq conteneurs contrôlés est à zéro ; cela décrit
l'instant de ce contrôle, pas un test de charge. Aucun montage de remplacement
de `fedow_core` ou `fedow_dashboard` n'est présent.

Les tunnels de cette tâche sont fermés. L'EC2 de démonstration est mise à
l'arrêt après les contrôles pour limiter le coût de calcul ; son disque,
son catalogue, ses secrets et ses sauvegardes sont conservés. Aix reste actif
et n'a pas été mis à cette release. L'ancienne base PostgreSQL Smoke et la
première tentative sont conservées dans les archives déjà indiquées.

## Limites et suite

- L'essai a sélectionné les commits explicites de la branche. Le déclencheur
  `main` existe dans AWS, mais une nouvelle création standard devra utiliser
  les corrections intégrées et revues dans `main`.
- Aucun déplacement de l'Elastic IP ni changement DNS : la pipeline Gala actif
  dans les deux sens et le TLS public du nouveau gala ne sont pas testés ici.
- La création d'un Checkout Stripe test est vérifiée. Aucun paiement, débit,
  crédit de recharge réel, vente à une caisse physique ni remboursement n'est
  exécuté. La remise à plat des remboursements reste reportée.
- L'envoi natif de l'invitation admin est journalisé, mais sa réception et la
  connexion par lien email restent à vérifier. Le parcours QR de test utilise
  un backend mail dummy.
- Les contrôles HTTP ne constituent ni une revue du rendu dans un navigateur,
  ni une validation de tous les cas métier, ni un test de concurrence en gala.

Les reçus et sondes temporaires sont sous `.context/first-boot/`, gitignoré.
Les preuves durables essentielles (commits, digests du manifeste, exécutions,
backup et limites) restent consignées dans ce document versionné.
