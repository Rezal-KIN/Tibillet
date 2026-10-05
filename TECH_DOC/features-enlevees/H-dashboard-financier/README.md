# H — Dashboard financier Gala retiré

Le 5 octobre 2026, l'utilisateur choisit de revenir au dashboard natif Fedow et
de supprimer les montages de remplacement. Le retrait porte uniquement sur ce
dashboard. Le parcours QR, la personnalisation web de Lespass et l'enregistrement
automatique des cartes restent conservés.

## Sources retirées et archive

Les quatre anciennes copies Gala (`views.py`, `urls.py`, `index.html`,
`suivi.html`) ont été importées sous `deploy/` par `0b7078ea`, puis apparaissent
dans le fork au merge `bc5b1a85`. Les copies de `base.html` et de l'accueil public
`public_index.html` ont été ajoutées par `e344ac69` pour les liens vers les sources,
puis les crédits ont été corrigés par `8e22ad78`.

L'[archive inactive](reference-7f31acd3.tar.gz) conserve les six fichiers
versionnés à l'identique depuis
`Rezal-KIN/Tibillet@7f31acd3cd5699dd83049aac94b017f9facccd29`. Son
`manifest.json` donne les chemins, blobs Git, tailles et SHA-256. Aucun fichier
runtime, secret ou contenu de base n'y est ajouté.

SHA-256 de l'archive :
`274a98de88d8be12a8f7d8720f02696035a22125d5c3b34fbf1d43dd8c84713a`.

Les six fichiers actifs de `deploy/Fedow/custom_patches/fedow_dashboard/` et
leurs six déclarations de volumes sont supprimés. L'archive n'est ni montée ni
chargée par Django. L'ancien suivi par bars/caisse, ses filtres et sa session
de suivi disparaissent, ainsi que les routes `/dashboard/suivi/` et
`/dashboard/suivi/data/`. Le script historique `reset_soldes.sh` conserve une
écriture de `suivi_session_start.txt` ; le dashboard natif ne lit pas ce fichier.
Ce script n'est pas exécuté lors du retrait.

## Retour exact à TiBillet

Référence : [`TiBillet/Fedow@1668d94`](https://github.com/TiBillet/Fedow/tree/1668d94fb2391cd1b9fef28abf857c356e13207c).
Image : `tibillet/fedow@sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83`.
Archive upstream SHA-256 :
`4532584ea066d01b9d69874f2285fa9a983ce49cb3e3ade84f76692a2d22bd24`.

Les fichiers inclus dans l'image reprennent directement la main. Aucun code
métier ni template équivalent n'est réécrit ou recopié dans le dépôt. La release
épinglée fixe cette référence ; le Compose de développement lancé seul avec
`latest` ne garantit pas le même rendu.

Les analyses natives du réseau et des monnaies, leurs caches et leurs graphiques
sont rétablis. Le comportement d'accès natif est conservé : l'accueil réseau est
public ; les vues de détail `asset_view` et `place_view` portent
`@staff_member_required`. Ce retrait ne rend donc pas tout Fedow privé.

Le lien vers les sources reste dans l'administration via le template partagé
existant ; `/source/` et l'en-tête HTTP `Link` restent servis par Nginx. Les liens
ajoutés au pied du dashboard et de l'accueil public disparaissent avec les
copies retirées. Aucune injection HTML ni nouvelle surcharge ne les remplace.
L'offre de sources continue de reconstruire Fedow depuis la référence et les
montages restants ; elle doit conserver tout `fedow_dashboard/` à l'identique.

Les montages de données SQLite, fichiers statiques, logs, settings, template
d'administration et Nginx restent présents. Ce retrait ne supprime pas tous les
volumes de la stack et ne change aucun solde ou transaction.

## Vérifications et limites

Le [vérificateur](../verify-restored-code.py) contrôle le checksum upstream et
l'absence de montage ou copie remplaçant le dashboard. Le
[reçu de restauration](restoration-receipt.json) conserve les références et les
empreintes des fichiers natifs. Pour reproduire ce contrôle depuis la racine :

```sh
python3 TECH_DOC/features-enlevees/verify-restored-code.py
python3 -m unittest discover -s deploy/tests -p test_source_offer.py -v
```

La [reconstruction des sources](source-reconstruction-receipt.json) utilise le
générateur existant, les archives upstream vérifiées et un dépôt Git temporaire
contenant les fichiers de montage actuels à l'identique. Les 54 fichiers de
`fedow_dashboard/`, assets compris, sont identiques octet par octet à la
référence dans l'archive Fedow produite. Aucun template `suivi.html` n'y est
ajouté. Les deux seuls overlays Fedow restants sont les settings et le template
partagé de sources dans l'administration. Les neuf tests existants de
publication des sources passent.

La [sonde du dashboard natif](native-dashboard-verification.json) exécute les
vues, modèles et templates originaux avec Django 4.2.30, SQLite en mémoire,
cache local et données fictives. Les onze requêtes de contrôle passent : accueil
anonyme et administrateur, accès refusé aux détails pour les visiteurs/comptes
ordinaires, détails monnaie/lieu ouverts aux administrateurs, anciennes routes
Gala absentes, administration avec lien de sources. Aucun SQL d'écriture n'est
exécuté par ces requêtes ; soldes et journal restent identiques. Le cycle de vie
monétaire affiche 10 euros créés, 7,50 en circulation et 2,50 dans le lieu. Le
second calcul utilise le cache sans requête SQL. L'absence de la courbe de survie
pré-calculée est tolérée par le code natif.

Cette sonde utilise un montage d'URL de test pour les seules routes dashboard et
admin. Elle ne démarre pas l'image Docker ni Memcached/Nginx et n'appelle aucun
service externe ; elle ne valide pas les API, un paiement ou la charge du gala.

Le retrait est local, sans push ni déploiement. La validation d'une nouvelle
instance et du parcours complet QR/recharge/caisse reste à effectuer avant le
gala. Les audits précédents sont conservés sans modification.

## Conditions d'une éventuelle réintroduction

Définir d'abord les informations nécessaires au gala et vérifier si le dashboard
natif les fournit. Si un ajout reste utile, privilégier une page séparée et
limitée, avec permissions explicites et calculs qualifiés. Ne pas réintroduire
ces anciennes copies complètes ni leurs montages sans nouvelle décision.
