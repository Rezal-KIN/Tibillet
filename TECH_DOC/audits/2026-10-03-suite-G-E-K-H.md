# Suite de l'audit : retrait G, correction E et explications I/J/K/H

Modifications locales du 3 octobre 2026. Le snapshot `2026-10-03-fork/` et ses
preuves sont conservés sans modification. Aucun push, déploiement, accès serveur
de production, paiement ou réparation de solde n'est exécuté dans ce lot.

## G — Retiré

L'utilisateur demande de se débarrasser de G et de reprendre TiBillet.
Le commit `35cc9918` retire la copie et le montage du serializer Fedow. Le fichier
natif de l'image reprend directement la main. Les références exactes, anciennes
fonctionnalités et résultats PostgreSQL locaux sont dans
[le dossier de retrait G](../features-enlevees/G-reparations-fedow.md).

## E — Correction minimale, fonction conservée

L'utilisateur conserve l'enregistrement d'une carte inconnue et demande la
solution la plus simple possible. Aucun helper partagé, nouveau module, modèle,
migration, nouveau retry automatique ou transaction distribuée n'est ajouté.

TiBillet distingue déjà les réponses dans `NFCCard.retrieve` :

| Réponse/erreur | Comportement après correction |
| --- | --- |
| 200 valide | Lire/synchroniser la carte comme auparavant |
| 404 / `FileNotFoundError` | Enregistrement local et distant déjà existant, puis relecture obligatoire |
| 403, 502, autre erreur HTTP, panne, timeout, réponse invalide | Refuser la vérification, sans tentative de création |
| Échec de l'enregistrement ou de la relecture | Erreur visible, aucun succès annoncé |

La correction concerne `DataAchatDepuisClientValidator.validate_tag_id` et
`check_carte`. Le premier retourne une erreur de validation DRF ; le second
affiche l'erreur dans la popup existante. Les détails techniques restent dans
les logs. La logique existante `get_or_create` conserve l'identité locale lors
d'une nouvelle tentative. Un conflit distant 409 reste suivi d'une relecture :
il n'est pas considéré, seul, comme une carte prête à l'emploi.

`_get` et `_post` sont copiés textuellement depuis la référence LaBoutik
`3fdba313c2dea172bfaa6a06ebab05e1caf62490`, commentaires compris. Ils retrouvent
le timeout natif `(3, 5)` : connexion de 3 secondes et lecture de 5 secondes.
Ce n'est pas une limite globale de durée du parcours complet. `_put` est inchangé.

Les autres écarts anciens de billets/adhésions ne sont pas modifiés par cette
correction ciblée. Les fichiers LaBoutik partagés ne sont donc pas entièrement
identiques à TiBillet et leurs montages restent présents.

Validation : huit tests de carte/réseau avec scénarios sur les deux points
d'entrée (scan et validation), cinq tests de prix/payload terminal et neuf tests
de publication des sources. Cas exercés : carte connue, nouvelle carte, 404 réel,
403/502/500, timeout/panne, réponse invalide, échec de création, conflit 409 suivi
d'une relecture, échec de relecture, reprise avec la même identité et deadlines
GET/POST. HTTP, ORM et authentification sont instrumentés : ce n'est pas une
validation d'une stack complète ni d'une vente réelle.

## I — Configuration Django inchangée, choix reporté

Les `settings.py` disent à Django quelle base/cache utiliser, quels domaines
accepter, comment envoyer les emails et où chercher les templates. Ils règlent
le fonctionnement de l'instance ; ils ne constituent pas un autre moteur métier.

Fedow utilise PostgreSQL par cette adaptation alors que sa référence choisit
SQLite par défaut et propose PostgreSQL en commentaire. LaBoutik et Lespass
utilisent déjà PostgreSQL dans leurs références. Retirer le fichier Fedow ne
convertit pas les données PostgreSQL : une éventuelle migration vers SQLite est
un chantier distinct. Les copies et leurs montages restent inchangés.

## J — Conservé pour l'instant

L'installateur reprenable LaBoutik et son montage restent en place. La pipeline
le relance après l'initialisation Lespass ; les appairages sont conservés.

## K — Conservé, dépendance de déploiement identifiée

Les liens ajoutés sont des ancres HTML. La page `/source/` est un fichier statique
servi par Nginx ; les archives sont téléchargées depuis les Releases GitHub.
Ces chemins ne lisent ni n'écrivent les soldes et ne font pas de requête Django
financière à chaque vente. Pas de défaut d'exécution du gala identifié dans K.

Ce n'est toutefois pas uniquement de la documentation :

- Les templates et la route statique doivent rester valides. Un défaut de
  template peut casser l'interface qui le charge ; un défaut Nginx peut affecter
  le proxy. Le template admin actuel a été rendu sans erreur avec Django 4.2.30,
  en vérifiant son héritage et son lien `/source/`.
- `deploy-release.sh` exige les sources exactes avant la mise à jour des stacks.
  Une image non reconnue, une archive manquante/incohérente ou GitHub indisponible
  peut arrêter cette tentative de déploiement. Il n'existe pas de contrôle GitHub
  périodique arrêtant l'instance en service.
- Après la mise à jour, le script vérifie aussi `/source/` : un échec empêche
  de marquer la release comme terminée, même si les applications démarrent.

Les neuf tests de publication passent. Cela ne constitue pas une simulation
de charge du gala. K est laissé en place ; sa dépendance à la pipeline est
documentée pour la prochaine discussion sur le déploiement.

## H — Erreurs expliquées, aucune modification

Les vues examinées ne modifient pas les soldes. Leur lecture peut néanmoins
échouer ou coûter des ressources partagées avec les opérations de caisse.

1. `_parse_suivi_filters` passe directement `place` au filtre UUID de Django.
   La valeur `invalid-uuid` lève une `ValidationError` non interceptée. Ce cas
   a été reproduit avec le vrai modèle et PostgreSQL local. Au chargement,
   la requête du dashboard peut retourner une erreur 500.
2. Au rafraîchissement, le JavaScript conserve les anciens chiffres quand
   la réponse échoue et écrit seulement dans la console du navigateur.
   L'utilisateur peut donc regarder des données qui ne sont plus actualisées.
3. `suivi` parcourt les métadonnées de toutes les ventes pour découvrir les bars.
   Plusieurs ouvertures/rafraîchissements produisent davantage de requêtes et
   peuvent ralentir les autres usages si les ressources deviennent insuffisantes.
   Aucun ralentissement de production ni seuil de charge n'est établi ici.
4. La différence recharges/dépenses sur une période n'est pas le solde réel
   disponible : elle ignore notamment le solde initial et les remboursements.

Les protections d'accès admin restent à examiner aussi. H est conservé dans
son état actuel ; l'utilisateur demande ici une explication, pas une refonte.
