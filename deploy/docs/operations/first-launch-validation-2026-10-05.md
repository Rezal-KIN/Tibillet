# Vérification d'un premier lancement — 5 et 6 octobre 2026

Objectif : créer une EC2 vide par Foundation, puis livrer exactement les images
validées par la pipeline Test. Les remboursements locaux restent hors périmètre.
Le gala Aix conserve son instance et son IP publique pendant cet essai.

## Défaut de retour Stripe découvert après les paiements test

Le 6 octobre, la carte QR `83f91f5a-5a33-434a-8664-3ba42b3f5926`
a reçu deux paiements Stripe **test** de 1 €. Une lecture de Stripe confirme
pour chaque Checkout `livemode=false`, `status=complete`,
`payment_status=paid`, `amount_total=100` et `currency=eur`. Fedow contient
une seule transaction `REF` de 100 centimes par Checkout, vers le portefeuille
actuel de cette carte ; le token fédéré vaut 200 centimes. Aucun paiement réel
n'est effectué par ces contrôles.

Le retour navigateur était en revanche cassé : les deux `success_url` et
`cancel_url` utilisent `festival.galas-am-aix.rezal.fr`, qui n'a pas de
résolution DNS. Le callback existe sur `galas-am-aix.rezal.fr`. Le lieu Fedow
est créé par l'installateur natif avant la réaffectation du domaine principal
Lespass par `configure_gala_apex` ; son champ `Place.lespass_domain` conservait
donc le sous-domaine initial.

Correction versionnée : après `configure_gala_apex`, le déploiement aligne
uniquement `Place.lespass_domain` du lieu apparié sur le domaine principal
approuvé. Les UUID du lieu et de son portefeuille sont lus dans le tenant
Lespass puis vérifiés dans Fedow ; un appariement incohérent ou un domaine
étranger bloque la correction. Le healthcheck contrôle ce réglage sans écrire.
Aucun modèle, migration, API, callback ou calcul de recharge n'est remplacé.
Les anciens Checkout payés conservent leur URL initiale chez Stripe ; les
nouveaux doivent utiliser l'apex. Les preuves non sensibles des lectures
SSM sont conservées dans `.context/first-boot/recharge-*-result.json`.

La régression locale sur un vrai ORM Django/SQLite vérifie l'ancien domaine,
sa correction idempotente, l'absence d'écriture du contrôle, la conservation
des autres champs et lieux, ainsi que le refus d'un portefeuille ou domaine
inattendu. Les cinq tests ciblés réussissent ; les sept unités TiBillet
restaurées restent identiques aux sources natives archivées.

**Résultat : Foundation, Test et Production réussies sur AWS.** Une nouvelle
instance a été créée, initialisée sans données préexistantes et redémarrée
sans réparation manuelle. Les accès admin, le site, les cartes, la lecture QR,
Celery, les sauvegardes et la restauration isolée ont été vérifiés. Un défaut
du contrôle admin a été corrigé et retesté avant la promotion. La PR #103
est ensuite fusionnée dans `main` le 6 octobre (heure de Paris) ; la pipeline
Test déclenchée automatiquement et la bascule publique sont aussi réussies.
La section complémentaire ci-dessous distingue ces contrôles de l'essai initial.
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

## Complément du 6 octobre : intégration et validation publique

La revue a confirmé les restaurations natives et l'absence de nouveau blocage.
Les 107 tests de déploiement passent à nouveau avant fusion ; les cinq contrôles
de politique, l'identité des sources restaurées et `git diff --check` sont valides.
La PR [#103](https://github.com/Rezal-KIN/Tibillet/pull/103) est fusionnée avec
le HEAD contrôlé `791711ed5791f8fe5d0bbab2269d59d5b948f1d4`, sans suppression
ni renommage de la branche. Commit de fusion :
`a219b5d6346dafdd8f0037e3dae5548962617c70`.

Le push dans `main` déclenche automatiquement Test par `WebhookV2` : exécution
`0f2c6544-b752-4400-a497-49628e2e5e1f`, statut final `Succeeded`.
Le déploiement SSM `9599ad8f-b0e4-4caa-bdb6-547b02d0c526` réussit en 5 min 15 s.
Le marqueur S3 `test-validated/smoke-a219b5d6346dafdd8f0037e3dae5548962617c70.json`
correspond au commit exact et aux digests attendus. Image Lespass construite :
`318629836660.dkr.ecr.eu-west-3.amazonaws.com/tibillet-gala-paris/lespass@sha256:a25cde4c34612ebfdb521b7929cdc7e81a972afc9a92a1833298b01fb3501a5f`.
Les images Fedow, LaBoutik et Traefik restent celles du manifeste initial.

La démonstration conserve sa release `v1.0.0` issue du commit `3a215c66`.
Le diff entre ce commit et le commit fusionné ne touche que trois documents
et le manifeste de release : les sources applicatives et les scripts runtime
testés sont identiques. Ce complément ne prétend pas avoir redéployé l'image
Lespass nouvellement construite sur la démonstration ou sur Aix.

L'EC2 de démonstration est démarrée puis activée temporairement par la pipeline
Gala actif, exécution `d83e5330-5035-4222-b598-b6d9f4ba6b7e`, statut `Succeeded`.
Le plan téléchargé est relu avant approbation : même commit `main`, cible
`i-00cb72994b875e92d`, ancien détenteur Aix `i-0801aa8a2273838aa`, même Elastic IP
`51.44.90.200`, groupe public et domaine attendus. Le contrôle local SSM
`0614a8f3-2c92-4892-9156-e955eff81310` réussit avant déplacement de l'IP.
La procédure versionnée redémarre Traefik puis vérifie le HTTPS strict avant
de changer le marqueur `active-gala`. Aucun changement DNS n'est effectué.

Les trois noms publics répondent 200 avec validation TLS activée, TLS 1.3 et
certificats Let's Encrypt couvrant leur nom. Les certificats observés expirent
le 3 janvier 2027. Les connexions admin des trois services, le refus d'un mauvais
mot de passe, l'alias cashless `/admin`, le formulaire QR, l'accueil et `/source/`
passent sur les domaines publics. Les quatre assets ont toujours les octets
attendus. Aucun navigateur contrôlable n'est connecté à cette session : ces
contrôles HTTP ne constituent pas une validation visuelle.

La carte de test `6F1992A1`, QR `74a4fee2-ad4f-42bb-ad48-3baae15d9732`, est prête
avec un portefeuille éphémère sans token ni transaction. La sonde SSM
`38c88767-95c5-4b6e-a98c-b25028edd533` confirme Stripe en mode réel ; la lecture
`e4eba74b-eb8f-43b9-8423-01ac0db55538` confirme qu'aucun parcours n'est encore
démarré sur cette carte à l'instant du contrôle. Un QR local est généré et
redécodé vers l'URL attendue. Aucun paiement n'est effectué par l'agent.
Une première sonde a échoué sur un mauvais répertoire d'exécution ; la sonde
corrigée utilise le répertoire et Poetry natifs, sans modification du serveur.

La réception de l'invitation admin et le parcours email restent à confirmer.
La connexion Gmail disponible dans cette session demande une réauthentification ;
elle n'a donc pas permis de vérifier la boîte de réception. Les remboursements
restent reportés. Les reçus complets, le plan, la sonde et le QR sont conservés
sous `.context/first-boot/` ; aucun mot de passe en clair n'est ajouté à ces fichiers.

## Choix utilisateur : poursuivre le paiement en mode test

L'utilisateur confirme ensuite avoir reçu l'invitation LaBoutik dans
`kin.rezal@gmail.com`. La réception est donc confirmée par le destinataire ;
la connexion via le lien n'est pas encore vérifiée.
Il demande de poursuivre sur l'instance de test sans argent réel.

Le retour vers Aix `f2cc606f-8a4e-47be-8b6e-937ae1ed832e` est arrêté au stade
d'approbation, avant toute application. La pipeline Gala actif cible ensuite
Smoke : exécution `d3ccea98-6931-40c5-8166-2d4ab5a0e027`, statut final `Succeeded`.
Le plan exact est téléchargé et contrôlé avant approbation : même commit `main`,
cible `i-0037b98572fccdff2`, ancien détenteur démonstration
`i-00cb72994b875e92d`, même IP, groupe public et domaine attendus.
Le contrôle local SSM `718eee1f-fa02-4252-b271-09cca8ac3c92` réussit.
Le marqueur `active-gala` devient `gala-smoke` après validation HTTPS stricte.

Les gardes réels confirment `STRIPE_TEST` et une clé `sk_test_` dans Fedow et
Lespass ; les valeurs des clés ne sont jamais imprimées. LaBoutik ne porte
pas de clé Stripe. Lespass utilise le backend email dummy sur Smoke : cette
instance ne vérifie donc pas la livraison SMTP réelle. Plusieurs erreurs
de la sonde temporaire (attribut Django absent puis guillemets shell) sont
corrigées avant tout scan ; aucune réparation applicative n'est nécessaire.

Un premier scan de préparation rencontre un timeout de lecture de 5 secondes
vers Fedow. La vue renvoie le message d'échec prévu et ne crée pas la carte.
La cause précise de ce délai n'est pas établie ; ce succès ultérieur ne vaut
pas test de charge. Une sonde de charge instantanée montre les conteneurs
principaux actifs et sans redémarrage. Après le contrôle local et la bascule,
SSM `37fcba7e-38ea-4f76-a81b-83baee475599` réussit : scan d'une nouvelle carte,
création dans LaBoutik/Fedow, puis deuxième scan sans doublon. La création
automatique native par signal et le traitement natif d'une carte déjà connue
fonctionnent aussi pendant ce contrôle.

Carte prête pour l'utilisateur : tag `BABBADAC`, QR
`83f91f5a-5a33-434a-8664-3ba42b3f5926`, URL
`https://galas-am-aix.rezal.fr/qr/83f91f5a-5a33-434a-8664-3ba42b3f5926/`.
Le QR local est généré et redécodé. La lecture SSM
`e3c8cb2f-9a7d-4124-8ecb-ad772035fcf6` confirme un portefeuille éphémère
sans token, transaction ni Checkout, en mode Stripe test.
Les trois authentifications admin, le refus d'un mauvais mot de passe,
l'alias `/admin`, les assets exacts, `/source/` et le formulaire QR passent
ensuite publiquement sur Smoke avec validation TLS activée.

Smoke reste temporairement actif pour permettre le paiement simulé par
l'utilisateur avec une carte de test Stripe. Le paiement et son crédit
ne sont pas encore exécutés à la clôture de cette préparation. La vérification
suivante devra comparer le montant payé en test, le solde et les transactions
Fedow, avant de rétablir Aix par la pipeline. Aucun paiement réel n'est requis
pour cette étape. L'EC2 de démonstration, désormais sans IP partagée ni groupe
public, est mise à l'arrêt ; son disque et ses sauvegardes restent conservés.
Aix est aussi conservée et aucune nouvelle release n'y est déployée.
