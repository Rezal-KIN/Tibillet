# Portage des personnalisations `Tibillet100J_OG`

État au 26 septembre 2026. Source : inventaire SSH du 22 septembre
([inventaire détaillé](tibillet100j-customizations-inventory.md)), archive exacte
[`legacy-100j-qr-flow`](../../Lespass/legacy-100j-qr-flow/README.md) et comparaison avec
`origin/main`. L'ancienne EC2 n'a pas été modifiée.

| Fonction historique | État dans la nouvelle base | Suite |
| --- | --- | --- |
| QR d'une carte neuve → email/prénom/nom → liaison → session immédiate → bouton « Recharger » | Porté dans `BaseBillet/views_qr_card.py`, routes et templates. L'email reste non vérifié et un courriel de validation est envoyé. Le parcours carte Fedow réelle → session → Checkout Stripe test a réussi sur Smoke. | Le bouton reste masqué par la configuration actuelle sur Smoke **et Aix** (`stripe_payouts_enabled=false`, `force_show_refill_button=false`). Vérifier le webhook et l'encaissement live avant de l'activer en production ; vérifier aussi un vrai email. |
| QR d'une carte déjà liée → notification/lien de connexion par email → page carte | Porté avec email QR dédié, limite d'un email par 5 minutes/carte et URL de retour signée. Un QR seul ne connecte plus le propriétaire. | Vérifier la délivrabilité Brevo et le retour après clic. |
| Email déjà connu + nouvelle carte | Adapté : lien de connexion obligatoire *avant* de lier la carte. | Vérifier compte sans carte, compte avec carte et refus de seconde carte. |
| Page QR « Carte liée ! » + accès direct au rechargement Stripe et à l'espace personnel | Portée dans le template `qr_landing.html`; le rechargement respecte `show_refill_button`. L'URL Checkout Stripe test a été créée avec succès, sans paiement. | Activer le bouton via une configuration reproductible seulement après vérification du webhook live et d'un paiement/remboursement contrôlé. |
| Page d'accueil principale et identité visuelle du gala 100 jours | Le rendu HTTP public de l'ancienne EC2 a permis de retrouver le panneau « carte cashless en 3 étapes » et l'ouverture de la connexion depuis le bouton d'adhésion ; ces éléments sont portés dans `reunion/views/home.html`. Les images/réglages de l'ancienne base restent hors archive QR. | Comparer visuellement les deux pages et récupérer les images/réglages non secrets si nécessaires. |
| Actions adhésion : facture, paiement hors ligne, annulation, renouvellement | Déjà présentes dans `BaseBillet/views.py` V2 (`MembershipMVT`). | Tests métier ciblés, sans recopier V1. |
| Limite par tarif, espace admin, page Faire Festival, permission d'initiation paiement | Déjà présents dans la V2 actuelle. | Vérifier le comportement gala, pas de portage source nécessaire. |
| Solde total fédéré/local, remboursement local par IBAN/BIC | Absent de V2 ; archive V1 disponible. Flux financier et documentaire non porté dans ce lot. | Spécifier données, permissions et tests avant migration. |
| Fedow `register_nfc_card` + outil `card_printer/` | Absent ; l'outil physique historique contient un ancien jeton en clair. | Récupérer le code sans la configuration, roter le jeton, sécuriser l'API et tester avec matériel. |
| Noms de bars historiques, ancien domaine nginx Laboutik | Spécifiques au gala précédent ; non repris tels quels. | Paramétrer par gala seulement si requis. |

## Écart de sécurité assumé

Le code historique ouvrait une session après la saisie d'un email même pour un compte déjà
existant. La V2 connectait aussi directement le propriétaire lors du scan d'une carte déjà
liée. Un QR imprimé et une adresse email ne prouvent pas l'identité du propriétaire : cette
reprise littérale aurait permis une usurpation. Le portage garde l'accès immédiat seulement
pour **un compte réellement nouveau** et demande un magic link pour tout compte ou toute
carte déjà liés. La confirmation de l'email reste nécessaire pour les opérations qui
l'exigent.

## Source complémentaire de la page d'accueil

Le 26 septembre, une requête HTTPS en lecture seule vers l'IP historique, avec l'en-tête
`Host: galas-am-aix.rezal.fr`, a permis d'observer le HTML de la page `/`. Aucun compte
ni secret n'a été utilisé. Le contenu visible indiquait « Comment fonctionne la carte
cashless ? » avec trois étapes et un bouton d'adhésion ouvrant le panneau de connexion.
La formulation « Aucun compte requis » de l'ancien panneau a été précisée : un email est
requis pour le rechargement en ligne via QR, mais le rechargement en caisse reste distinct.

La vérification Smoke a révélé que l'installateur TiBillet associait initialement l'apex
au tenant générique `public` : le healthcheck HTTP 200 passait alors que l'accueil du gala
restait sous `festival.`. Le contrat de déploiement réconcilie désormais ce mapping après
`install`, et le healthcheck vérifie le propriétaire du domaine. La correction est
versionnée dans la pipeline, pas appliquée manuellement à l'EC2.

Sur un gala inactif, le certificat HTTPS local de Fedow est temporairement
auto-signé. Les appels serveur de Lespass utilisent donc le service `fedow_nginx`
sur le réseau Docker local, avec le `Host` public et les signatures d'API
inchangées. Les autres installations TiBillet conservent leur HTTPS public ;
aucune désactivation globale de la vérification TLS n'a été ajoutée.

## Validation avant activation publique

1. **Fait sur Smoke le 26 septembre :** 9 tests ciblés ; E2E avec une carte Fedow
   créée pour le test, inscription, liaison wallet, session immédiate, bouton
   simulé activé et création d'un Checkout Stripe test sans paiement. La
   pipeline Test du commit `1b0740fe99cccfd9e872be27c2266e37cd50751c`
   a réussi. Aucun réglage d'EC2 n'a été modifié manuellement.
2. **À faire avant d'exposer la recharge live :** vérifier la configuration
   du webhook Stripe live, effectuer un paiement réel contrôlé, confirmer le
   crédit cashless et un remboursement, puis activer le bouton via une
   configuration versionnée. La présence d'une clé live ne prouve pas ce flux.
3. **À faire avant de déclarer le portage complet :** tester la délivrabilité
   Brevo et le retour du lien signé ; une carte déjà liée dans un autre
   navigateur, un autre compte et une deuxième carte ; comparer le rendu
   mobile et les images/réglages de l'ancien accueil.
4. Promouvoir un manifeste immuable via la pipeline Production et son
   approbation manuelle ; ne pas modifier directement l'EC2 Aix ni déplacer
   l'IP publique pour ce test.
