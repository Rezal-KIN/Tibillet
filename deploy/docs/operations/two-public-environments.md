# Test CAWL et production publics séparés sur AWS

Cette option remplace, pour le test CAWL, l'usage historique de l'IP et des
noms de production par Smoke. Elle est désactivée par défaut et s'active par
deux opérations Foundation explicites. La réservation d'une IP ne signifie
pas que l'application est déployée ou que le DNS a changé.

| Environnement | EC2 | Domaine Lespass | Intégrations communes |
|---|---|---|---|
| Test CAWL | `gala-smoke-cawl` | `gala-test.rezal.fr` | `integrations-stripe-test`, section CAWL test |
| Production | gala dédié, par exemple `bapts2026` | `galas-am-aix.rezal.fr` | `integrations-stripe-live`, section CAWL live |

Chaque environnement conserve ses bases, son secret généré et ses clés de
pairing. Les noms Fedow et LaBoutik sont respectivement `fedow.` et `cashless.`
devant le domaine Lespass. Le nom historique des secrets communs ne sélectionne
pas Stripe : le fournisseur est fixé par `payment_provider` dans le catalogue.
La Smoke Stripe reste une référence distincte, sans obligation de la démarrer
pour travailler sur CAWL. Ne pas prendre une branche nommée `production` pour
une preuve de déploiement AWS.

## Ordre des opérations

1. **Inventorier et fixer les sources.** Vérifier le compte `318629836660`,
   Paris, le catalogue S3, les instances, leur identité et les pipelines.
   Foundation lit normalement `main` ; les applications CAWL proviennent de
   `migration/cawl-payments`. Les changements runtime communs doivent être
   présents dans les deux branches avant utilisation. Une révision explicite
   de pipeline est possible ; consigner son SHA et son résultat final.
2. **Réserver l'adresse test.** Exécuter la Foundation standard avec
   `GalaName = Reserve CAWL Test Address`. Le plan n'autorise que la création
   d'une EIP test non associée. Il ne déplace aucune IP, ne change aucun domaine
   et ne démarre aucune application. Le catalogue conserve
   `public_cawl_test_address_reserved=true` pour les exécutions suivantes.
3. **Valider la candidate.** Après une sauvegarde Smoke fraîche explicitement
   autorisée, déployer la candidate CAWL sur Smoke et vérifier le résultat Test
   complet, ses images et ses parcours. Les modifications de domaine ne sont
   pas encore activées. Les images auxiliaires des fichiers release sont
   épinglées aux digests de la Smoke de référence, sans changer leurs versions.
4. **Livrer la production.** Créer le gala par Foundation CAWL, puis préparer
   un manifeste dont le commit, les images et les lots de cartes correspondent
   à la preuve Smoke. Publier son offre de sources exacte. Suivre validation,
   approbation humaine du manifeste, déploiement et contrôles sur cette EC2.
   Le premier déploiement attend lui aussi une sauvegarde autorisée avant
   finalisation. Contrôler les clés, modes CAWL et permissions des secrets.
5. **Activer la production.** Utiliser la pipeline Gala actif avec le gala réel.
   Elle conserve l'EIP de production et ses DNS existants ; elle vérifie la
   cible, le TLS et les retours avant d'enregistrer le marqueur actif.
6. **Séparer le test.** Exécuter la Foundation standard avec
   `GalaName = Enable Public CAWL Test`. La réservation doit déjà être inscrite
   au catalogue. L'association de l'EIP test est refusée tant que Smoke détient
   l'EIP ou le marqueur actif de production. Le plan n'autorise que cette
   association, HTTP/HTTPS sur le groupe propre à Smoke CAWL, les domaines
   passés aux documents SSM et les recalculs IAM attendus. Aucune destruction.
7. **Adapter le test et publier son DNS.** Remplacer seulement les trois
   domaines du champ `site` du secret commun dev. Préserver les autres champs
   et la version précédente. Redéployer la candidate depuis son commit testé.
   La migration runtime vérifie les trois pairings avant écriture et ne modifie
   que les domaines, adresses internes et URL d'événements internes de Smoke.
   Elle conserve identifiants, clés, cartes, soldes et écritures financières.
   Préparer puis faire approuver les trois PUT et le refresh OVH, avec leurs
   valeurs exactes, l'état frais, les contrôles et leur retour limité.
8. **Valider les deux entrées.** Vérifier la résolution autoritaire et récursive,
   le TLS et les trois services de chaque environnement, les liens email/QR,
   les recharges, paiements et remboursements. Vérifier les notifications CAWL
   signées et les états du ledger. Une page HTTP 200 ou un diagnostic API `OK`
   ne valide pas ces parcours. Tester le matériel de caisse séparément.

Les callbacks entre Lespass, Fedow et LaBoutik passent par le gateway Docker
de leur propre EC2, jamais par l'IP du gala actif d'un autre environnement.
Les healthchecks vérifient ces mappings. La production reçoit le courrier
natif ; le test conserve la redirection de tous les destinataires vers la
boîte de test. Ne pas activer les clés live dans Smoke.

## DNS OVH et préservation du local

Conserver la zone enfant et la délégation de `gala-test.rezal.fr`. Les seules
cibles normalement nécessaires sont l'A apex vers l'EIP test, puis les deux
CNAME `cashless` et `fedow` vers `gala-test.rezal.fr.`. Conserver les TTL et les
autres enregistrements. Utiliser un accès limité aux lectures de cette zone,
aux PUT des trois IDs vérifiés et au refresh ; aucun DELETE n'est nécessaire.
Le refresh publie toute la zone enfant : contrôler les changements concurrents.

Si les noms de production pointent déjà vers l'EIP partagée conservée,
ne pas les réécrire. Ne modifier ni `taramis`, ni Estia, ni les NS, le courrier,
les certificats locaux ou les services voisins. Le retour vers le local est
une opération DNS limitée aux mêmes enregistrements, depuis leur état sauvegardé,
et non une restauration globale de zone. Le DNS seul ne rapatrie pas les données
produites sur AWS : définir cette reprise avant toute future migration métier.

Références : [livraison](new-gala-deployment-and-development-workflow.md),
[secrets](active-gala-and-shared-integrations.md),
[sauvegardes](backup-restore.md).
