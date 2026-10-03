# D — Limite de terminaux retirée

- **Origine** : présente dans `30c571bc` (3 mai 2026), importée par `bc5b1a85`.
- **Retrait** : `e27aa554`.
- **Décision** : retirer le système ; abandonner la proposition de le réimplémenter.

## Fonctionnement retiré

Le point de vente nommé `caisse` était limité à deux terminaux. Une liste en
Memcached conservait l'ordre d'arrivée. Un troisième terminal désactivait le plus
ancien (`Appareil.actif=False`). Les appareils dont le nom commençait par `admin`
étaient exemptés. Des gardes forçaient la reconnexion des appareils évincés dans
l'accueil, la préparation, le scan de carte et le paiement ; une carte primaire
pouvait aussi réactiver l'appareil. L'action `register_pos_connection` avait été
ajoutée pour cette logique.

## Retour au standard

Les trois helpers, leurs constantes, l'action dédiée et les points d'appel sont
retirés. Les fonctions `index`, `preparation` et `paiement`, décorateurs compris,
sont recopiées exactement depuis la référence TiBillet LaBoutik épinglée.
L'authentification et l'appairage natifs sont conservés. Il n'existe plus de quota
personnalisé, de file FIFO ni d'exemption fondée sur le nom de l'appareil.

`check_carte` conserve E (enregistrement d'une carte inconnue) ; seul le garde D
y est supprimé. Ce fichier ne doit donc pas être présenté comme entièrement
identique à upstream. Les autres écarts déjà identifiés, notamment les contrôles
d'adhésion manquants dans l'ancienne copie, restent recensés dans l'audit.

Aucune table de sessions n'a été ajoutée. Les appareils précédemment désactivés
dans une base existante ne sont pas réactivés automatiquement par le retrait du
code : vérifier ces appareils au déploiement et utiliser le circuit natif de
connexion/appairage. Aucun état de production n'a été modifié dans ce lot.

## Retrouver la version retirée

```sh
git show e27aa554^:deploy/Laboutik/views.py
git show e27aa554 -- deploy/Laboutik/views.py
```

## Conditions d'une éventuelle réintroduction

La proposition d'une nouvelle table PostgreSQL a été refusée et n'a pas été
implémentée. Réexaminer d'abord le besoin et les possibilités natives de TiBillet.
Une réintroduction exige une nouvelle décision utilisateur et des essais
concurrents d'admission, d'éviction, de reconnexion et d'accès aux autres points
de vente. Ne pas remettre l'ancien fichier complet de vues : il écraserait aussi
les fonctions et corrections upstream sans rapport avec la limite de terminaux.
