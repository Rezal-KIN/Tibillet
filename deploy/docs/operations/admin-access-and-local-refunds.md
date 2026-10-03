# Administration et remboursements du gala

## Remboursements des rechargements sur place

Vérification du 3 octobre 2026 : le code applicatif courant et la release Aix
v1.0.10 n'exposent pas le formulaire historique de demande de remboursement
des rechargements en espèces ou par terminal bancaire sur place.

- `BaseBillet/views.py:MyAccount.refund_online` sélectionne exclusivement le
  token dont l'asset est `is_stripe_primary` et appelle Fedow pour Stripe.
- `BaseBillet/templates/reunion/views/account/balance.html` invite le titulaire
  d'un solde local à contacter l'organisateur. Il ne collecte aucune demande.
- L'archive `deploy/Lespass/legacy-100j-qr-flow/source/Lespass/custom_patches/`
  conserve les vues et les routes `/my_account/refund_local_form/` et
  `/my_account/refund_local_success/`. La vue relit le solde côté serveur,
  collecte nom, prénom, IBAN/BIC et pièce d'identité, puis enregistre une
  `LocalRefundRequest` et envoie des notifications. Elle ne réalise pas le
  virement bancaire ni le débit cashless.
- L'archive référence `BaseBillet/refund_models.py`, mais ce fichier et les
  templates de remboursement ne font pas partie de l'archive QR. Leur présence
  historique est documentée dans l'inventaire 100J ; le portage reste à faire.

La possibilité de rembourser en caisse ne remplace donc pas l'ancien suivi
des demandes. Pour rétablir ce parcours, il faut définir la réservation du
solde demandé, prévenir les demandes et paiements doubles, suivre le paiement
effectif et le débit cashless, et protéger les coordonnées bancaires et
justificatifs. La présence de code ne démontre pas à elle seule une conformité
juridique. Aucun remboursement ni mouvement de portefeuille n'a été exécuté
pendant cette vérification.

## Accès d'administration

Les administrations du gala sont accessibles aux adresses suivantes :

- Lespass : `https://galas-am-aix.rezal.fr/admin/`.
- Fedow : `https://fedow.galas-am-aix.rezal.fr/admin/`.
- Laboutik : `https://cashless.galas-am-aix.rezal.fr/admin/`, alias de
  `/adminstaff/`. `/adminmembre/` reste accessible avec les mêmes comptes.

Sur une installation Gala (`GALA_APEX_TENANT=1`), Lespass affiche le formulaire
Django de connexion par mot de passe. La connexion par mail depuis la page
publique reste disponible. Les autres installations conservent leur parcours
de connexion par mail à l'entrée de l'administration.

Après déploiement, exécuter sur l'instance cible :

```sh
python3 /opt/tibillet-gala/repository/deploy/tools/runtime/configure-gala-admin.py \
  --gala gala-am-aix --username admin --apply
```

Le script demande le mot de passe sans l'afficher, vérifie les trois comptes
avant modification et réutilise les comptes administrateurs d'installation.
Leurs emails et relations métier sont conservés. Fedow reçoit un compte
administrateur si aucun n'existe. Seule l'empreinte Django est stockée en base ;
aucun mot de passe n'est enregistré dans le dépôt, les manifestes ou les logs.
Un nom déjà attribué à un autre compte est refusé. Les sauvegardes des bases
conservent les accès entre les releases ; le script n'est pas exécuté
automatiquement à chaque déploiement.
