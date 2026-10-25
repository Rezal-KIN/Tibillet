# Exceptions et actions à effectuer

Mise à jour de périmètre du 16 octobre 2026 : abonnements automatiques, TPE
bancaires connectés et répartition des fonds entre organisations sont exclus
définitivement par décision utilisateur. Leur absence ne bloque pas la production
Gala. Le remboursement du solde rechargé en ligne est, lui, requis ; son parcours
et ses contrôles sont documentés dans
[le périmètre CAWL et les remboursements](../../../deploy/docs/operations/cawl-scope-and-wallet-refunds.md).

## Avant une qualification de production

| Priorité | Exception / action | Pourquoi / critère de fermeture |
| --- | --- | --- |
| P0 | Identifier le contrat API exact et les capacités du marchand | Le prestataire CAWL est confirmé ; les accès et l'offre technique réelle du compte restent à vérifier |
| P0 | Qualifier le parcours HCP et les captures en sandbox | Identifiants test, callbacks publics, états réels et contrôle de montant/référence |
| P0 | Étendre la non-régression Lespass aux parcours complets | Les 8 tests CAWL PostgreSQL passent ; les adhésions réelles, Crowds, skins, emails et tâches distantes restent à éprouver |
| P0 | Tester le transport signé Lespass → Fedow | Les tests de ledger ne remplacent pas l'authentification et la liaison des services en déploiement |
| P0 | Tester la synchronisation CW avec l'image LaBoutik réelle | Validation du choix, création du moyen, traitement de vente et de refund, export et absence de doublon |
| P0 | Construire et vérifier les images et l'offre de sources | Copies explicites, dépendance SDK et manifeste de release cohérent |
| P0 | Adapter l'ARN et les permissions du secret d'intégration | Le champ historique du runtime peut désigner CAWL ; IAM/IaC distante doit autoriser ce secret |
| P0 | Inventorier puis vider ou suivre les paiements Stripe en attente | Une bascule qui coupe le webhook ne doit pas abandonner un débit déjà soumis |
| P0 | Rapprocher les remboursements de quantité de billets identiques | Vérifier les cas multi-quantité, multi-ligne, partiel puis total et refus PSP, avec règles métier réelles |
| P0 | Qualifier les accès multi-tenant et le changement de mode | Un tenant ne doit pas encaisser sur le compte d'un autre ; test/live et marchand restent immuables par opération |

## Différences fonctionnelles explicites

| Fonction | État de la branche | Action pour une parité complète |
| --- | --- | --- |
| Paiement ponctuel EUR | Implémenté, qualification réelle requise | Paiements sandbox puis release candidate testée |
| Recharge Gala | Implémentée avec ledger natif, tests monétaires isolés | Parcours navigateur et signatures entre services, panne réseau et concurrence multi-worker |
| Prix libre Lespass | Montant validé avant HCP | Vérifier les formulaires de tous les skins, familles et prix libres multiples |
| Adhésion/réservation gratuite | Parcours métier existant | Non-régression : aucun appel PSP pour zéro |
| Validation manuelle d'adhésion | Porte d'entrée conservée | Vérifier acceptation admin, lien de paiement, soumission en attente et refus |
| Contribution Crowds | Finalisation explicite CAWL | Tester navigateur fermé, callback répété et unicité de l'email |
| Refund réservation/billet | Journal, demande API et confirmation ajoutés | Sandbox refus/attente/succès, rapprochement, limites de quantité et reprise après interruption |
| Refund du portefeuille fédéré | Parcours CAWL avec réservation native Fedow et remboursement des recharges d'origine | Qualifier la livraison et le remboursement auprès du prestataire ; voir le document de périmètre |
| Abonnement automatique CAWL | Hors périmètre définitif ; tarifs récurrents refusés avant appel PSP | Aucune implémentation prévue, décision utilisateur du 16 octobre 2026 |
| Abonnements Stripe existants | Historique conservé, aucune conversion | Arrêter ou maintenir leur suivi dans Stripe ; réinscription CAWL suivant le contrat du marchand |
| Mandat SEPA existant | Aucun transfert implémenté | Confirmer support CAWL, réautorisation et traitements différés/refus/retours |
| Onboarding Connect automatique | Hors périmètre définitif ; refusé en mode CAWL | Aucune implémentation prévue dans cette intégration Gala |
| Reversement fédéré inter-organisations | Hors périmètre définitif ; `transfer.created` Stripe désactivé | Aucune implémentation prévue, décision utilisateur du 16 octobre 2026 |
| Terminal WisePOS | Hors périmètre définitif ; routes Stripe Fedow désactivées | Aucune implémentation prévue ; lecteurs NFC cashless distincts et conservés |
| Devises autres que EUR | Refus explicite | Paramétrage marchand, calculs et tests par devise, sans réutiliser implicitement l'unité des tokens |
| Session HCP expirée sans ID paiement connu | Reprise automatique incomplète | Recherche/rapprochement marchand qualifié ; ne pas recréer un débit en cas d'incertitude |
| Capture/refund contesté ou chargeback | Pas de mécanisme dédié ajouté | Événements réels du contrat, journal, rapprochement et procédure pour fonds déjà dépensés |

## Points de reprise opérationnelle à approfondir

1. Un remboursement accepté par CAWL peut précéder la sauvegarde locale de son
   identifiant. La clé déterministe protège les reprises dans la période
   d'idempotence du PSP ; une interruption prolongée exige un rapprochement
   avant de soumettre de nouveau l'opération.
2. Le journal de callback distingue événement et effet financier. Les tests de
   concurrence à plusieurs workers doivent vérifier les courses entre un
   callback et un retour navigateur, sur la base réellement déployée.
3. Un paiement capturé suivi d'une panne de synchronisation ne doit pas être
   recapturé. Corriger la synchronisation de la vente existante.
4. Un refund PSP d'une recharge ne doit pas laisser en circulation une monnaie
   remboursée. Le parcours réserve désormais les sommes dans le journal natif
   avant soumission bancaire et restitue uniquement un refus définitif. Sa
   qualification doit vérifier les cas décrits dans le document de périmètre.
5. La désactivation de Stripe coupe ses nouveaux appels, mais l'ancien stock de
   factures, mandats et refunds doit continuer à être rapproché dans son
   prestataire d'origine.

## Nettoyage après stabilisation

- Conserver les migrations anciennes pour la reconstruction des bases.
- Distinguer suppression de code SDK, renommage des champs historiques et
  migration réelle des contrats de paiement.
- Renommer les helpers et URLs legacy dans une version séparée avec compatibilité
  des liens et des clients API.
- Réviser les libellés d'administration, catalogues de traduction, OpenAPI,
  commandes historiques, documents d'aide et rapports de paiement.
- Retirer la dépendance Stripe seulement après fermeture de ses parcours utiles
  et mise à jour des tests historiques ; le mode CAWL actuel la conserve comme
  dépendance de compatibilité, tout en bloquant ses opérations concernées.

La qualification de production porte sur le **périmètre Gala convenu**, et non
sur un remplacement de toutes les capacités de Stripe. Les exclusions
définitives ci-dessus ne constituent pas une liste d'implémentations futures.
