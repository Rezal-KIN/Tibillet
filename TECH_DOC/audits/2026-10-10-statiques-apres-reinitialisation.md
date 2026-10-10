# Styles refusés après réinitialisation — 10 octobre 2026

Après la remise à zéro Smoke/Aix, la page HTML répondait 200 mais ses cinq
feuilles CSS répondaient 403. Le navigateur affichait donc le site sans Bootstrap
ni personnalisation Gala. Les fichiers de style étaient bien présents dans
l'image ; leur contenu n'avait pas été supprimé.

## Cause constatée

La procédure ponctuelle d'archivage utilisait `umask 077`, adapté aux sauvegardes
et configurations privées. Son `git restore deploy/Lespass/www` a également
recréé les deux fichiers statiques suivis par Git et leurs dossiers avec ce
masque : quatre dossiers en 0700 et deux fichiers en 0600. Django, UID 1000,
pouvait les lire ; Nginx, UID 101, ne pouvait pas traverser les dossiers.
`collectstatic` n'a pas changé les permissions des fichiers déjà présents.
Les fichiers nouveaux, comme Bootstrap, étaient bien en 0644, mais derrière
un dossier inaccessible.

La préparation existante corrigeait le propriétaire et le dossier `www` en
0755, sans corriger ses sous-dossiers. Le contrôle existant vérifiait les
pages, les appairages et le worker, mais pas les assets. Son succès ne prouvait
donc pas que l'interface avait chargé ses styles. Le défaut venait de notre
procédure de réinitialisation ; aucune erreur de TiBillet amont n'est établie.

## Correction appliquée

Les seuls fichiers statiques publics Lespass ont retrouvé des dossiers 0755
et fichiers 0644 sur les deux hôtes. Quatre dossiers et deux fichiers ont
changé de mode sur chacun. Le contenu des fichiers, les bases, médias privés,
secrets et images applicatives sont conservés. Les applications n'ont pas été
redémarrées et les domaines restent sur Smoke Stripe TEST.

Commandes SSM réussies :

- Smoke : `456617a8-1289-4d1c-83b6-8159e9a3fc2b`.
- Aix : `977fd9bb-f428-4806-acc7-cf3d50274300`.

Après correction, les cinq CSS et les six autres assets directement appelés
par la page publique répondent tous 200 avec TLS vérifié. Le test local de
chaque hôte vérifie aussi CSS, JavaScript et favicon.

## Prévention dans nos scripts hôte

`prepare_writable_mounts` normalise uniquement les permissions sous
`www/static`, avant le démarrage Compose. Les liens symboliques ne sont pas
suivis. Les permissions des médias privés, logs, bases et configurations ne
sont pas élargies par cette correction.

`healthcheck.sh` exige maintenant un HTTP 200, sans redirection, pour chacune
des cinq feuilles de style réellement référencées par la page d'accueil.
Une page HTML disponible avec des CSS bloqués ne valide plus une livraison.

Les tests de régression exécutent la fonction Bash sur un arbre en 0700/0600
et vérifient la préservation d'un média privé et d'un fichier extérieur lié par
symlink. Le test du healthcheck vérifie le refus de CSS 403/404 lorsque la page
et les autres services répondent correctement.
Validation locale : 151 tests réussis, dont 3 ignorés ; les deux tests ciblés
ont été rejoués après la liste finale des cinq CSS. Syntaxe Bash vérifiée.

Le CSS public est identique octet par octet à la source personnalisée de
l'image. Les six fichiers de polices qu'il référence répondent aussi 200.

Les deux scripts hôte corrigés sont livrés séparément, avec vérification des
empreintes avant remplacement et conservation de leurs versions précédentes.
Cette livraison ne reconstruit pas les images et ne relance pas les installateurs
ni l'import de cartes. Le prochain lancement de pipeline utilisera aussi ces
scripts depuis `main`.
