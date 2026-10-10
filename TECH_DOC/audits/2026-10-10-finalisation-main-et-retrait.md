# Finalisation de main et retrait des essais — 10 octobre 2026

Suite autorisée du [réalignement](2026-10-10-realignement-deploiement.md).
L'utilisateur a demandé d'exécuter les étapes restantes. Les preuves historiques
de livraison restent conservées, avec leur date et leurs limites.

## Intégration

La PR #106 est fusionnée dans `main`, commit
`f33f83daec304cf5b3f81fa775c7d03130611bf3`. La référence JSON du test Smoke final
a été corrigée avant fusion : le test exact du code `60147839` est
`cc69c084-ae14-4438-b558-24d0827807ae`, vérifié en succès dans AWS.

La pipeline Test du commit de main est lancée manuellement, son déclenchement
automatique étant désactivé. Son exécution est
`06c9b842-2b48-4e2f-bf17-0b2c039ab11c` ; son résultat sera consigné après contrôle.

## Retrait précis des deux essais

| Gala | EC2 | Disque original | Snapshot privé conservé |
| --- | --- | --- | --- |
| Premier démarrage interrompu | `i-0fb1dd7f460d6d88d` | `vol-029ab722ab927334d` | `snap-0b451152f049f9908` |
| Démarrage corrigé et reboot | `i-03a85efbda0291201` | `vol-0ea485dd48a918a26` | `snap-095d819c58f31b22a` |

Les snapshots sont demandés sur les disques arrêtés avant toute suppression.
Leur état `completed`, leur propriétaire, leur chiffrement et leur disque source
doivent être vérifiés. Les sauvegardes S3 et offres de sources restent conservées.

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

## Recette et résultats restant à consigner

La recette se fait sur Smoke en Stripe TEST. Elle distingue connexion admin,
recharge payée en mode test, validation du retour/webhook et réception d'un email
adressé uniquement à la boîte de test configurée. Un scan physique nécessite une
carte et un lecteur : il ne peut pas être prouvé par un appel HTTP seul.
