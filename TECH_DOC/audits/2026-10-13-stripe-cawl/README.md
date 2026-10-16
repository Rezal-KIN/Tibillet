# Audit Stripe et migration CAWL — TiBillet / Lespass / Gala

Audit commencé le 13 octobre 2026, arrêté pour revue le 14 octobre 2026.
Prestataire cible : **CAWL, Crédit Agricole / Worldline**.

**Décision de périmètre du 16 octobre 2026 :** renouvellements automatiques,
TPE bancaires connectés et répartition des fonds entre organisations sont
définitivement hors périmètre. Le remboursement du solde rechargé en ligne est
requis. Voir [le périmètre actuel et le fonctionnement du remboursement](../../../deploy/docs/operations/cawl-scope-and-wallet-refunds.md).

Livraison limitée à la branche, à la demande de l'utilisateur. Aucun déploiement
ni modification de production. Le remplacement fonctionnel complet reste à
achever ; les exclusions sont recensées dans le chapitre 6.

Ce dossier contient l'inventaire de Stripe dans le dépôt, l'analyse des parcours,
les différences avec l'API Direct CAWL, l'implémentation dans une branche isolée,
les exceptions et le plan de déploiement. L'intégration utilise la documentation
publique CAWL e-commerce. Le contrat et les identifiants du marchand n'ont pas
été fournis ; la qualification réelle du compte CAWL reste à effectuer.

## Point de départ et sauvegardes

| Élément | Référence |
| --- | --- |
| Dépôt | `/workspace/Tibillet` |
| Révision auditée | `1e5e60951e30c74fa9dae3f50f9f680ece1f2b72` |
| Branche reçue dans l'environnement | `work` ; aucune branche locale `main` ni référence distante présente |
| Branche de travail | `migration/cawl-payments` |
| Première copie | `backup/stripe-baseline-2026-10-13`, au commit initial |
| Deuxième copie | `/workspace/scratch/tibillet-stripe-baseline-2026-10-13.tar.gz` |
| SHA-256 de l'archive | `a1a8e9a9052a6429684f6b2887541d24c64c8e3a1008e1f4d006cdf7d2dcb8a6` |

La branche d'origine et la référence de sauvegarde restent au commit initial.
L'archive contient les fichiers suivis de ce commit. Les bases de production,
les secrets et les fichiers ignorés ne font pas partie de cette archive.

## Lecture du dossier

1. [Cartographie des paiements et analyse du code](01-cartographie.md).
2. [Correspondances Stripe → CAWL et différences](02-comparaison-cawl.md).
3. [Modifications réalisées dans la branche](03-implementation.md).
4. [Déploiement, configuration, rapprochement et retour arrière](04-deploiement.md).
5. [Vérifications et limites de la qualification](05-verifications.md).
6. [Exceptions et actions restantes](06-exceptions-actions.md).
7. [Consignes pour la revue par un autre agent](07-revue-agent.md).

Les annexes sont exploitables avec un tableur ou un script :

| Annexe | Contenu |
| --- | --- |
| [files.tsv](inventory/files.tsv) | Tous les chemins contenant Stripe dans la révision initiale, rôle et nombre de lignes |
| [references.tsv](inventory/references.tsv) | Chaque emplacement : chemin, ligne, symbole englobant et identifiants |
| [symbols.tsv](inventory/symbols.tsv) | Classes, fonctions et portées de module contenant des références |
| [sdk-calls.tsv](inventory/sdk-calls.tsv) | Appels syntaxiques au SDK et localisation précise |
| [call-sites.tsv](inventory/call-sites.tsv) | Appels aux helpers et couches indirectes portant le nom Stripe |
| [summary.json](inventory/summary.json) | Révision, totaux, limites et SHA-256 des annexes |
| [Inventaire Fedow](inventory/fedow/summary.json) | Archive épinglée : chemins, références, symboles et appels SDK dans `inventory/fedow/` |
| [Inventaire LaBoutik](inventory/laboutik/summary.json) | Même inventaire pour l'archive LaBoutik dans `inventory/laboutik/` |
| [changes.tsv](inventory/changes.tsv) | Fichiers livrés dans le diff de la branche par rapport à la sauvegarde |

## Résultats structurants

L'inventaire initial porte sur **1 834 fichiers suivis**, dont **331 contiennent
Stripe**, pour **3 636 lignes correspondantes**. Les fichiers sont répartis en
application, interfaces, déploiement, tests, migrations historiques et archives.
Les 31 emplacements d'appels SDK applicatifs Lespass utilisent 16 opérations
Stripe distinctes. Les appels présents dans une archive ou un commentaire ne
sont pas considérés comme une preuve d'exécution.

Les archives sources vérifiées ajoutent 69 fichiers et 1 133 lignes pour Fedow,
74 fichiers et 477 lignes pour LaBoutik. Les recherches textuelles incluent les
noms CSS tels que `striped` ; ces totaux ne mesurent pas des fonctions de paiement.
Les inventaires Python repèrent respectivement 13 et 10 appels syntaxiques au SDK.

Deux architectures doivent être distinguées :

- Lespass contient Stripe Connect pour les billets et adhésions de chaque tenant.
- Les recharges Gala utilisent le compte Stripe central de Fedow. La commande
  `configure_gala_refill` permet explicitement ce parcours sans compte Connect
  Lespass. La présence du code Connect ne démontre donc pas l'existence d'un
  compte Connect pour votre gala.

L'historique disponible contient la création de comptes Connect au moins depuis
`9fb8e5e6`, le 19 septembre 2024. Le code actuel crée des comptes **Standard** ;
une ancienne spécification mentionne Express et ne constitue pas la référence
pour ce détail.

La branche prépare les nouveaux paiements ponctuels CAWL, les callbacks signés,
le crédit Fedow et le suivi des remboursements de réservation. La sélection
`PAYMENT_PROVIDER=cawl` coupe l'accès aux clés Stripe et aux routes Stripe
concernées. Le mode par défaut reste `stripe` pour rendre la bascule explicite.
Les exceptions répertoriées doivent être résolues ou acceptées avant d'utiliser
CAWL en production. Aucun changement de production n'a été effectué.

## Reproduire l'inventaire

```sh
python3 TECH_DOC/audits/2026-10-13-stripe-cawl/tools/inventory.py \
  --revision backup/stripe-baseline-2026-10-13 \
  --output /tmp/inventaire-stripe-initial
```

La recherche n'accède ni au réseau ni aux secrets. Elle lit les fichiers texte
suivis par Git à une révision précise et exporte les identifiants, sans contenu
de configuration. Les limites de recherche statique figurent dans `summary.json`.

## Sources externes

- [Documentation CAWL e-commerce](https://docs.ecommerce.cawl-solutions.fr/fr/index).
- [SDK Python officiel](https://docs.ecommerce.cawl-solutions.fr/en/integration/how-to-integrate/server-sdks/python).
- [Dépôt du SDK utilisé par CAWL](https://github.com/Online-Payments/sdk-python3).
- Sources des images : `deploy/source/image-sources.json` ; archives Fedow et
  LaBoutik récupérées aux commits épinglés et contrôlées par SHA-256.
