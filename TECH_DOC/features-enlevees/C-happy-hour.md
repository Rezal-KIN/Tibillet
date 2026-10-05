# C — Happy hour retiré

- **Origine** : présent dans `30c571bc` (3 mai 2026), importé par `bc5b1a85` (21 septembre).
- **Retrait** : `4e20db20`.
- **Décision** : suppression demandée ; privilégier les prix natifs TiBillet.

## Fonctionnement retiré

Une plage horaire et un JSON propre au serveur modifiaient les prix envoyés au
terminal. Le validateur du total utilisait la même grille et modifiait aussi le
prix de l'objet article en mémoire pour la requête. Deux scripts dédiés créaient
le catalogue/grille et ses alias de bar.

## Retour au standard

Les prix sont ceux des articles en base. La méthode
`DataAchatDepuisClientValidator.validate_articles` est copiée textuellement depuis
la référence TiBillet LaBoutik épinglée. Le retrait de D restaure ensuite la fonction
`index` complète de cette référence, qui sérialise les prix sans surcharge horaire.
Les anciens helpers, variables d'exemple et scripts happy hour sont retirés.

Les articles, l'historique des ventes et le JSON runtime existant sont conservés.
Le JSON et les anciennes variables n'agissent plus sur ce code. Lors d'un futur
déploiement, rafraîchir les terminaux pour éviter un ancien prix remisé en cache,
qui sera désormais refusé par le contrôle de total natif.

## Retrouver la version retirée

Le commit précédent au retrait contient le code et les scripts :

```sh
git show 4e20db20^:deploy/Laboutik/views.py
git show 4e20db20^:deploy/Laboutik/validators.py
git show 4e20db20^:deploy/tools/scripts/hh_seed.py
git show 4e20db20^:deploy/tools/scripts/hh_alias_fix.py
git show 4e20db20 -- deploy/Laboutik deploy/tools/scripts deploy/README.md
```

## Conditions d'une éventuelle réintroduction

Vérifier d'abord si la version TiBillet retenue propose un mécanisme natif adapté.
Si une personnalisation reste demandée, documenter sa différence exacte avec les
sources upstream et tester la cohérence prix affiché/total débité, le passage de
la plage horaire et les terminaux avec ancien payload. Ne pas réintroduire une
ancienne copie complète des vues/validateurs ni exécuter le script de catalogue
sur une base existante sans examiner ses mises à jour.
