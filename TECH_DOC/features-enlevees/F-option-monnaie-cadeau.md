# F — Option de synchronisation cadeau retirée

- **Origine** : présente dans `30c571bc` (3 mai 2026), importée par `bc5b1a85`.
- **Retrait** : `50a6906f`.
- **Décision confirmée** : revenir au fonctionnement TiBillet standard, y compris
  sa synchronisation native de la monnaie cadeau.

## Personnalisation retirée

`ENABLE_GIFT_ASSET_SYNC`, désactivé par défaut, conditionnait la publication de
la monnaie cadeau vers Fedow. La monnaie locale était toujours publiée.

## Retour au standard

La méthode `FedowAPI.send_assets_from_cashless` est copiée textuellement depuis
`TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`. Elle publie la monnaie
locale (`TLF`) et la monnaie cadeau (`TNF`) comme le fait TiBillet. L'ancienne
variable n'est plus lue ; elle ne change plus le comportement, même à `0`.

Ce retrait peut donc rendre la monnaie cadeau visible dans Fedow lors d'une
initialisation/synchronisation ultérieure. Il ne distribue pas de crédit aux
clients et ne supprime aucune monnaie ou donnée. Le bootstrap standard suppose
que les moyens de paiement locaux correspondants existent ; vérifier son parcours
sur une stack isolée avant promotion. Aucun bootstrap de production n'a été lancé.

## Retrouver la version retirée

```sh
git show 50a6906f^:deploy/Laboutik/fedow_api.py
git show 50a6906f -- deploy/Laboutik/fedow_api.py deploy/README.md
```

## Conditions d'une éventuelle réintroduction

L'option n'a plus de besoin exprimé. Si elle est redemandée, vérifier d'abord un
réglage natif TiBillet, documenter l'effet sur les actifs déjà présents et tester
les initialisations répétées avec l'option activée/désactivée. Conserver une
différence minimale avec la méthode upstream ; ne pas réintroduire l'ancien
fichier complet de communication Fedow.
