# Finalisation de main et retrait des essais — 10 octobre 2026

Suite autorisée du [réalignement](2026-10-10-realignement-deploiement.md).
L'utilisateur a demandé d'exécuter les étapes restantes. Les preuves historiques
de livraison restent conservées, avec leur date et leurs limites.

## Intégration

La PR #106 est fusionnée dans `main`, commit
`f33f83daec304cf5b3f81fa775c7d03130611bf3`. La référence JSON du test Smoke final
a été corrigée avant fusion : le test exact du code `60147839` est
`cc69c084-ae14-4438-b558-24d0827807ae`, vérifié en succès dans AWS.

Le déclencheur V2 lance automatiquement Test lors des pushes de `main`, même si
l'action Source indique `DetectChanges=false`. L'exécution automatique
`eaba99ea-0a21-428b-a68e-a7b31a299e23` a réussi, déploiement Smoke compris.
Le doublon manuel `06c9b842-2b48-4e2f-bf17-0b2c039ab11c` a été arrêté avant
DeploySmoke. La PR #107 est également fusionnée, commit
`2832050a1e1a2553e38f699393b6086bb7425bc9`.

## Retrait précis des deux essais

| Gala | EC2 | Disque original | Snapshot privé conservé |
| --- | --- | --- | --- |
| Premier démarrage interrompu | `i-0fb1dd7f460d6d88d` | `vol-029ab722ab927334d` | `snap-0b451152f049f9908` |
| Démarrage corrigé et reboot | `i-03a85efbda0291201` | `vol-0ea485dd48a918a26` | `snap-095d819c58f31b22a` |

Les snapshots ont été effectués sur les disques arrêtés avant toute suppression.
Leur état `completed`, leur propriétaire `318629836660`, leur chiffrement et leur
disque source sont vérifiés. Les sauvegardes S3 et offres de sources sont conservées.

Le mécanisme de retrait Foundation existant est étendu aux deux identités exactes :

1. `Prepare Gala Alignment Retirement` déplace les deux adresses Terraform vers
   la ressource de retrait, sans recréation d'EC2, puis change uniquement leurs
   protections de suppression et `DeleteOnTermination`.
2. `Retire Gala Alignment` retire leurs EC2/disques et leurs routes de livraison,
   tout en conservant les entrées du catalogue, les secrets et les archives.

Les plans refusent les identités ou disques différents, toute mutation d'Aix/Smoke
et les changements IAM hors retrait des seuls droits des hôtes supprimés. La
vérification finale refuse un essai actif, exige les snapshots privés achevés,
puis constate la disparition des EC2 et disques avant de valider le catalogue.
Les hôtes d'essai peuvent rester arrêtés pendant la préparation.

Validation locale : 148 tests exécutés, 3 ignorés ; vérification Terraform du
format et contrôle du diff. Aucun code métier TiBillet n'est changé pour ce retrait.

La préparation Foundation `155f879f-f54f-4be4-bb4c-3b82ccc0f91d` est réussie :
deux mises à jour EC2 en place, sans création ni suppression. Le premier plan de
retrait `bb55bc03-7392-4245-b03c-e3589a69e07f` a été refusé avant application,
car les journaux CloudWatch et les rôles IAM auraient aussi été supprimés.
Les deux essais sont ajoutés à la liste existante de conservation des journaux
et rôles. Le garde-fou continue de refuser leur suppression. Le second plan
`82968173-7f03-4164-b849-6a4688303b66` a été refusé avant application, car Terraform
diffère aussi le calcul des politiques de livraison de trois autres galas.
La correction accepte uniquement les valeurs calculées par le provider, pour
les trois identités existantes exactes, sans changer rôle, identité ou autre champ.
Les modifications explicites de droits restent interdites.

Le retrait Foundation `96f1d983-efa7-43da-91df-e6e5244abb6d` a ensuite réussi.
Le plan revu contient 16 suppressions : les deux EC2 et sept ressources de livraison
pour chaque essai. Les neuf politiques de livraison recalculées sont identiques
aux politiques précédentes après application ; la dixième politique est celle
de bascule active, dont seuls les droits des hôtes retirés ont disparu comme prévu.
Les deux EC2 sont `terminated` et les deux disques sont absents. Snapshots privés
chiffrés, sauvegardes S3, journaux, rôles sans droits et entrées de catalogue restent
conservés. Aucun hôte Aix ou Smoke n'a été remplacé. Validation locale finale :
149 tests, dont 3 ignorés.

## Recette effectuée

Les trois formulaires publics ont été soumis avec les accès communs autorisés :
Lespass `/admin/`, Fedow `/admin/` et LaBoutik `/adminstaff/` affichent chacun le
dashboard authentifié. Fedow s'affiche correctement en navigation privée.

La recharge du portefeuille natif sur Smoke a ouvert un Checkout Stripe TEST.
La session est vérifiée `livemode=false`, `paid`, `complete`, montant 100 centimes.
Fedow contient une seule transaction créditant 100 centimes au portefeuille.
Deux relectures du retour renvoient HTTP 302 vers `/my_account/` sans modifier
le crédit ni les transactions. Le webhook natif a répondu HTTP 200 le
10 octobre à 14:45:15 UTC. Aucun paiement LIVE n'a été effectué.

Le backend SMTP natif a accepté un message adressé exclusivement à la boîte de
test configurée (`sent_count=1`, TLS actif), depuis Aix qui autorise cette sortie.
Sujet : `TiBillet - recette Gala 10 octobre - 87d53e94`. L'utilisateur a confirmé
la réception dans `kin.rezal@gmail.com`. Smoke conserve son backend email dummy.

Le test QR existant a été exécuté sur les services réels de Smoke : création
signée par LaBoutik, liaison à un portefeuille, page de recharge et création de
Checkout TEST. Résultat : `1 passed`, sans paiement supplémentaire. La vérification
TLS a été conservée. Le lanceur de recette reprend le script du dépôt et indique
le chemin absolu de Poetry utilisé par les images ; il ne monte aucun fichier.
La carte synthétique est déclarée perdue par le nettoyage natif du test.

Le rendu natif `/my_account/tokens_table/` renvoie HTTP 200 et affiche le crédit
de 1 euro ; le portefeuille et les transactions de recette sont conservés.

Un scan physique nécessite une carte et un lecteur : il ne peut pas être prouvé
par un appel HTTP seul. La promotion `gala-am-aix-native-20261010-v3` doit reprendre
exactement les quatre images et les trois lots du dernier Test main réussi.
Son déploiement et la comparaison finale des images Aix/Smoke restent à consigner.
