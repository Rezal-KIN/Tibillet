# Réinitialisation native Smoke et Aix — 10 octobre 2026

L'utilisateur a validé l'inventaire final, demandé le retrait des variables
PostgreSQL résiduelles de Fedow et choisi de réinitialiser **les deux instances**.
Les bases, médias et caches courants sont archivés avant remplacement. Les
anciennes archives Aix du réalignement précédent restent conservées.

## Retrait des variables inutilisées

La PR #110 est fusionnée dans `main`, commit
`64044190b7ea780a0270a1c231468252897e5cc2`.
`POSTGRES_DB`, `POSTGRES_USER` et `POSTGRES_PASSWORD` ne sont plus rendus dans
`fedow.env`. Les nouveaux secrets n'incluent plus `fedow_postgres_password`.
Le champ est seulement toléré dans les secrets anciens pour ne pas renouveler
les autres clés. Les paramètres PostgreSQL Lespass et LaBoutik sont conservés.
Aucun code métier, modèle, migration ou calcul financier TiBillet n'est modifié.
Validation locale : 150 tests exécutés, 3 ignorés, succès.

## Archivage effectué avant la remise à zéro

| Instance | EC2 conservée | Sauvegarde restaurée isolément | Archive locale |
| --- | --- | --- | --- |
| Aix | `i-0801aa8a2273838aa` | `20261010T155817Z` | `/var/lib/tibillet-gala/gala-am-aix/native-reset-archives/20261010T155817Z` |
| Smoke | `i-0037b98572fccdff2` | `20261010T160013Z` | `/var/lib/tibillet-gala/gala-smoke/native-reset-archives/20261010T160013Z` |

Les quatre processus applicatifs ont été arrêtés pendant les dumps pour figer
les écritures. Les sauvegardes S3 contiennent deux dumps PostgreSQL et un
snapshot SQLite cohérent. La restauration isolée vérifie 59 tables LaBoutik,
180 Lespass pour Aix et 1 620 pour l'ancien Smoke, ainsi que l'intégrité et les
clés étrangères SQLite. Les configurations privées et RDB Redis ont été
archivés dans S3, téléchargés à nouveau et comparés octet par octet.

Après ces contrôles seulement, les dossiers complets des trois bases et leurs
médias ont été déplacés dans les archives locales. Les anciens volumes Redis
ne sont pas effacés. Les conteneurs de données/caches/applications et Nginx ont
été retirés pour que Compose les recrée ; TLS, EIP, disques et anciennes archives
restent en place. La préparation SQLite native est explicitement remise à l'état
`initializing`, sans modification du code de Fedow.

La première commande d'archivage Aix s'est arrêtée immédiatement sur le shell
SSM, avant toute écriture. Le même travail a ensuite été exécuté explicitement
dans Bash. Commandes effectives réussies :
`c57039d2-ec0c-447f-80bf-74787f699484` pour Aix et
`dae0463f-8287-4455-a09c-2c7d73a3b5e7` pour Smoke.

## Livraison par les pipelines

Le Test `f814bb89-f156-44ed-b30e-df8de3636f28` a réussi sur le commit `64044190`,
DeploySmoke compris. Sa commande SSM de livraison est
`f47b0063-34dc-417b-9c94-72403332f5b1`, également réussie.
La transition DeploySmoke a été temporairement retenue pendant les archives,
puis réactivée. Le déploiement reconstruit les bases et appairages par les
commandes natives, configure les comptes et réimporte les trois lots de cartes.

Le manifeste Aix préparé est
`releases/gala-am-aix/gala-am-aix-native-20261010-v4.json`, avec les images de ce
Test et le catalogue de 7 020 cartes. Son [offre de sources correspondantes](https://github.com/Rezal-KIN/Tibillet/releases/tag/sources-gala-am-aix-native-20261010-v4-64044190b7ea)
est publiée, avec les huit fichiers et leurs empreintes contrôlés.

La pipeline Production Aix `97022329-aaf3-4b0b-b8f0-d87e2c504c62` a réussi.
L'approbation porte sur le ZIP validé au commit manifeste
`ea0109028695a206ad824fa2f5165852ccc3764b`, son empreinte
`b3ebe9c02c8bf65861be74a4c6bd5d05ea7dc169a299548f458efdfdb2c8d4b0`,
les images Test et la cible EC2 exacte. La commande SSM
`ce65fe5b-969b-4c46-8fe2-3bbc0a3296fb` a réussi en 8 minutes 16 secondes.

## Résultat vérifié sur les deux instances

| Contrôle après réinitialisation | Smoke | Aix |
| --- | ---: | ---: |
| Cartes du stock importées, trois lots | 7 020 | 7 020 |
| Cartes associées à un porteur/portefeuille éphémère | 0 | 0 |
| Checkouts Stripe | 0 | 0 |
| Soldes de tokens positifs | 0 | 0 |
| Transactions liées à un paiement Stripe | 0 | 0 |
| Ventes LaBoutik | 0 | 0 |
| Comptes admin prêts | 3 | 3 |
| Applications locales HTTP 200 | 3 | 3 |
| Worker Celery | Répond | Répond |
| Vérification de l'import natif | 7 020 existantes, 0 ajoutée | 7 020 existantes, 0 ajoutée |
| Variables PostgreSQL Fedow, fichier et conteneur | Absentes | Absentes |
| Montage de code applicatif ou CSV | Aucun | Aucun |
| Mode Stripe | TEST | LIVE, inactif |

Les quatre images applicatives/reverse proxy sont identiques à l'empreinte
près sur les deux hôtes. Les bases et secrets restent propres à chaque Gala.
Les deux bases PostgreSQL natives Lespass/LaBoutik et le SQLite natif Fedow
sont neufs ; leurs appairages ont été reconstruits par les installateurs.

Contrôles complets réussis :
`357420d7-e4d5-4730-93a3-eab691878a0f` pour Smoke et
`394fac02-dd7f-4ee8-b1fb-c269ec9727a1` pour Aix.
Les nouvelles sauvegardes sont également restaurées dans des conteneurs
isolés, avec 59 tables LaBoutik, 180 tables Lespass, intégrité et clés
étrangères SQLite vérifiées :

| Instance | Nouvelle sauvegarde | Commande de restauration isolée réussie |
| --- | --- | --- |
| Smoke | `20261010T160949Z` | `90dfaa40-88b2-4e36-9792-e9ba1f329931` |
| Aix | `20261010T162151Z` | `3f39c22e-7ced-4da2-9b1c-caf863602953` |

Les marqueurs de préparation sont classés comme terminés, avec leur reçu
conservé dans chaque archive. Les unités de démarrage et timers de sauvegarde
sont actifs. Les [preuves assainies](2026-10-10-reinitialisation-native-preuves.json)
conservent les empreintes communes, références SSM et états vérifiés ; aucun
secret ou lien entre identifiants de carte n'y figure.

## Domaine actif et essais utilisateur

L'EIP `51.44.90.200` reste sur Smoke `i-0037b98572fccdff2` ; le marqueur
SSM `/tibillet-gala-paris/active-gala` vaut `gala-smoke`. Les trois domaines
publics répondent HTTP 200 avec vérification TLS normale :

- https://galas-am-aix.rezal.fr/
- https://cashless.galas-am-aix.rezal.fr/
- https://fedow.galas-am-aix.rezal.fr/

Aix est réinitialisée et prête, mais ne reçoit pas le trafic public.
Les anciennes sessions, inscriptions et configurations de terminaux dépendant
des bases archivées doivent être recréées ou reconnectées pour les essais.
Aucun paiement ni porteur/carte synthétique n'a été créé après la remise à zéro.
Les vérifications ci-dessus sont des contrôles techniques de l'état initial ;
le nouveau parcours physique et la recharge Stripe sont laissés à l'utilisateur.

La clôture documentaire et le manifeste figé ne nécessitent pas une nouvelle
construction applicative. L'exécution Test déclenchée par leur fusion est
arrêtée avant DeploySmoke afin de conserver les images déjà vérifiées communes
aux deux hôtes. Le déclencheur V2 et la transition DeploySmoke restent actifs
pour les prochains changements.
