# Inventaire des modifications internes TiBillet

Audit en lecture seule du 3 octobre 2026. Aucun correctif ni déploiement exécuté pendant cet audit.

## Base exacte de comparaison

- Dépôt initial : `TiBillet/Lespass`, branche `main`.
- Commit au départ du fork : `fd7680891c31bbdf6215e7a0750074de89ff5e8e`, du 20 septembre 2026. Le dépôt du fork a été créé le 21 septembre 2026.
- Preuve amont : https://github.com/TiBillet/Lespass/commit/fd7680891c31bbdf6215e7a0750074de89ff5e8e
- L'historique du fork a été réécrit : le commit équivalent dans l'histoire actuelle est `f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9`. Les deux commits ont exactement le même arbre Git : `1c1816a9fed44f433ea31e8711968c0cf246a384`. Leurs contenus sont donc identiques, malgré leurs identifiants différents.
- État actuel comparé : `origin/main`, commit `84982241faa555035982f425569a44fc44db77c4` (PR #102 fusionnée). Les fichiers applicatifs et les surcharges Fedow/Laboutik examinés sont également identiques à ceux du commit applicatif `3cfd531b4ca3c9953f27ca06b2391cadcf33db00` de la release Aix v1.0.11.
- Les champs `fork_commit` et `tibillet_upstream_commit` des manifestes de release actuels désignent le commit applicatif testé du fork ; ils ne donnent pas le commit initial TiBillet ci-dessus.

La comparaison Lespass ci-dessous est un diff de contenu entre deux versions précises, pas une comparaison avec la dernière version publiée par TiBillet. Les nombres de lignes sont les additions/suppressions du diff ; ils incluent commentaires et mise en forme.

## Lespass : 16 fichiers applicatifs concernés

10 fichiers existants modifiés et 6 fichiers ajoutés, pour 492 lignes ajoutées / 24 supprimées dans ces 16 fichiers.

| Fichier | État / lignes + / - | Changement et raison |
| --- | --- | --- |
| `BaseBillet/views_qr_card.py` | Ajout / 194 / 0 | Nouveau parcours carte NFC par QR : recherche Fedow, bon domaine d'origine, inscription, liaison carte/portefeuille, rattachement des adhésions trouvées par numéro imprimé, page carte et envoi du lien email. Récupère le parcours rapide des 100J. Un compte nouveau peut entrer immédiatement, avec email encore non vérifié ; un compte déjà connu doit ouvrir son lien email avant la liaison. Une carte déjà liée ne connecte pas son propriétaire sur le seul scan ; un autre utilisateur connecté reçoit 403. Limite d'envoi : un email par carte/utilisateur toutes les cinq minutes via le cache. |
| `BaseBillet/urls.py` | Modifié / 5 / 0 | Ajoute `/qr/link/`, `/qr/check-email/<uuid>/`, `/qr/<uuid>/` avant le routeur DRF existant, afin que le nouveau parcours reçoive ces requêtes. |
| `AuthBillet/utils.py` | Modifié / 6 / 6 | `sender_mail_connect` accepte un template d'email ; `get_or_create_user` peut retourner `(utilisateur, créé)` via une option. Le parcours QR doit distinguer un nouveau compte d'un compte existant. Les appels sans option gardent leur type de retour. Le mécanisme `transaction.on_commit` était déjà dans TiBillet au départ du fork. |
| `BaseBillet/tasks.py` | Modifié / 0 / 2 | Retire des logs l'URL complète de connexion et l'URL de retour. Évite d'enregistrer le lien d'authentification dans les journaux ; l'envoi du mail reste assuré par la tâche existante. |
| `BaseBillet/templates/reunion/views/register.html` | Modifié / 2 / 2 | Ajoute une explication sur la recharge et le jeton CSRF du formulaire ; supprime les logs navigateur affichant l'email. Le formulaire utilise le parcours QR. |
| `BaseBillet/templates/reunion/views/qr_landing.html` | Ajout / 32 / 0 | Page « Carte liée », bouton de recharge via le parcours Fedow/Stripe existant, accès au compte et rappel de confirmation email. Le bouton respecte `show_refill_button`. |
| `BaseBillet/templates/reunion/views/qr_check_email.html` | Ajout / 15 / 0 | Page demandant d'ouvrir le lien email quand le compte ou la carte sont déjà connus. |
| `BaseBillet/templates/emails/qr_connexion.html` | Ajout / 25 / 0 | Email spécifique à l'accès à la carte, avec retour vers sa page après connexion. |
| `BaseBillet/templates/reunion/views/home.html` | Modifié / 45 / 2 | Rétablit le guide cashless en trois étapes observé sur les 100J. Le bouton d'adhésion ouvre le panneau de connexion pour un visiteur non connecté ; conserve l'accès aux adhésions pour un utilisateur connecté. |
| `Administration/management/commands/configure_gala_apex.py` | Ajout / 66 / 0 | Associe le domaine principal au tenant Gala, plutôt qu'au site public générique créé par l'installateur. Évite d'afficher le mauvais accueil et d'envoyer les liens QR/email au mauvais domaine. Commande répétable et contrôlable avec `--check`, réservée à `GALA_APEX_TENANT=1`. |
| `Administration/management/commands/configure_gala_refill.py` | Ajout / 59 / 0 | Active le réglage existant `force_show_refill_button` pour les galas utilisant Stripe via Fedow sans compte de versement Stripe Connect Lespass. Vérifie le mode et les credentials, refuse d'écraser un masquage explicite. Commande répétable avec `--check`. Ne change pas le modèle `Configuration`. |
| `fedow_connect/fedow_api.py` | Modifié / 21 / 4 | Avec `GALA_LOCAL_FEDOW=1`, les appels Lespass → Fedow utilisent `http://fedow_nginx` dans le réseau Docker, avec le Host public et les signatures existantes. Évite d'appeler le gala actif via son DNS lorsqu'on prépare un autre gala ; évite le certificat local temporaire. Hors de ce mode, HTTPS public est conservé. |
| `TiBillet/settings.py` | Modifié / 5 / 4 | Lit TLS/SSL SMTP comme des booléens via `== '1'`, plutôt que des chaînes où `'0'` est vraie. Corrige l'incompatibilité TLS+SSL qui bloquait les emails. Rend `EMAIL_BACKEND` configurable pour les tests sans email sortant. |
| `Administration/admin/site.py` | Modifié / 6 / 4 | Sous `GALA_APEX_TENANT=1`, propose le formulaire Django par mot de passe. Sinon, redirige vers `/?login=1` pour ouvrir la connexion mail. Répond au besoin d'accès administrateur commun demandé pour Aix. Les permissions du site ne sont pas réécrites. |
| `Administration/admin/dashboard.py` | Modifié / 6 / 0 | Ajoute dans l'administration le lien `/source/` vers le code de l'instance, pour l'offre de sources AGPL. |
| `seo/templates/seo/partials/tibillet_community_links.html` | Modifié / 5 / 0 | Ajoute le même accès aux sources dans les liens publics. |

Traçabilité principale : PR #71 (QR), #72 (accueil), #73 (domaine), #74 (Fedow local), commit `47f027ae` (emails/admin), #91 (bouton recharge), #94/#98 (sources/crédits), #102 (connexion admin par mot de passe). Les changements sont attribués par le diff et l'historique des fichiers, pas par le nombre total de commits du dépôt importé.

### Ce qui n'a pas changé dans Lespass depuis le fork

Le diff est vide pour les migrations, `BaseBillet/models.py`, `AuthBillet/models.py`, `Customers/models.py`, `BaseBillet/views.py`, le template `BaseBillet/templates/reunion/views/account/balance.html`, `pyproject.toml` et `poetry.lock`.

Le formulaire de remboursement local des 100J n'existait pas dans cette base forkée : il appartient à l'ancienne personnalisation Lespass, partiellement archivée sous `deploy/Lespass/legacy-100j-qr-flow/`. Ce lot n'a donc pas supprimé ce formulaire de la base initiale ; il n'a pas été porté dans le code actif. Le parcours Stripe actuel de `BaseBillet/views.py` n'a pas été réécrit par le fork.

## Fedow et Laboutik : du code applicatif aussi présent sous deploy/

Le dépôt forké est Lespass. Fedow et Laboutik sont deux projets TiBillet distincts, fournis par leurs images. Docker Compose monte des fichiers de ce dépôt à la place de certains fichiers internes de ces images. Par conséquent, exclure tout `deploy/` cacherait des modifications métier importantes.

Les personnalisations ci-dessous ont été importées depuis le déploiement historique le 21 septembre 2026. Pour les gros fichiers `serializers.py`, `views.py`, `validators.py` et `fedow_api.py`, la comparaison entre ce premier import et l'état actuel ne montre que l'ajout des notices d'auteurs/licence. Leur contenu métier n'a pas été écrit dans les récentes corrections de pipeline.

Sources de référence des images épinglées, identifiées dans `deploy/source/image-sources.json` :

- Fedow : `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c` (6 septembre 2026).
- Laboutik : `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490` (22 juillet 2026).
- Les archives sources ont été relues après vérification de leur SHA-256 contre ce catalogue. Les diffs sont présents à côté de ce rapport et leurs correspondances dans `overlays.json`.

### Fedow

| Fichier dans notre dépôt → fichier interne remplacé | Rôle / raison observable |
| --- | --- |
| `deploy/Fedow/settings.py` → `fedowallet_django/settings.py` | PostgreSQL à la place de SQLite, hôtes adaptés et recherche des templates de sources. Réglages d'exploitation du gala. |
| `deploy/Fedow/custom_patches/fedow_core/serializers.py` → `fedow_core/serializers.py` | Personnalisation des validations monétaires : création d'un portefeuille pour un utilisateur existant qui n'en a pas ; création du premier bloc d'une monnaie lors d'une recharge si absent. Le remplacement entier présente également les écarts décrits plus bas ; aucune justification contemporaine n'a été trouvée pour chaque différence. |
| `deploy/Fedow/custom_patches/fedow_dashboard/views.py` → `fedow_dashboard/views.py` | Suivi des recharges, dépenses et soldes, séries par minute et filtres lieu/bar/créneau. La copie remplace aussi des fonctions du dashboard réseau amont. |
| `deploy/Fedow/custom_patches/fedow_dashboard/urls.py` → `fedow_dashboard/urls.py` | Ajoute `/dashboard/suivi/` et `/dashboard/suivi/data/`. |
| `deploy/Fedow/custom_patches/fedow_dashboard/index.html` → `fedow_dashboard/templates/index/index.html` | Accueil du dashboard simplifié et bouton « Suivi financier ». |
| `deploy/Fedow/custom_patches/fedow_dashboard/suivi.html` → `fedow_dashboard/templates/index/suivi.html` | Nouvelle interface des graphiques et filtres de suivi, actualisée périodiquement. |
| `deploy/Fedow/custom_patches/fedow_dashboard/base.html` → `fedow_dashboard/templates/base.html` | Ajout du lien de sources AGPL. |
| `deploy/Fedow/custom_patches/fedow_dashboard/public_index.html` → `fedow_dashboard/templates/index.html` | Ajout du lien de sources sur l'accueil public. |

Les noms `PIAN'S`, `oenol'ss` et `shots` restent dans le code de suivi. Ce sont des valeurs héritées d'un gala, pas des fonctions génériques TiBillet.

### Laboutik

| Fichier dans notre dépôt → fichier interne remplacé | Rôle / raison observable |
| --- | --- |
| `deploy/Laboutik/settings.py` → `Cashless/settings.py` | Même correction des booléens SMTP que Lespass, backend email configurable et templates de sources. |
| `deploy/Laboutik/install.py` → `administration/management/commands/install.py` | Reprise d'une installation interrompue : ne refait pas les appairages Lespass/Fedow déjà enregistrés, refuse un changement silencieux de destination, évite les recréations d'admin et emails d'activation répétés. Correction de bootstrap ajoutée après l'import. |
| `deploy/Laboutik/views.py` → `webview/views.py` | Happy hour affiché en caisse ; limite de deux terminaux simultanés sur le point de vente nommé `caisse`, avec exclusion du plus ancien et exception pour un terminal dont le nom commence par `admin` ; réactivation par carte primaire ; tentative d'enregistrement des cartes inconnues. Présente aussi les écarts amont décrits plus bas. |
| `deploy/Laboutik/validators.py` → `webview/validators.py` | Applique les prix happy hour côté serveur lors de la validation du montant, et tente de créer dans Fedow une carte introuvable. Les prix viennent de `www/happy_hour_prices.json`, avec horaires par défaut 22:00–23:30 et cache de 60 secondes. Présence du code ne signifie pas que ce fichier de prix est configuré. |
| `deploy/Laboutik/fedow_api.py` → `fedow_connect/fedow_api.py` | Synchronisation de la monnaie cadeau optionnelle, désactivée par défaut via `ENABLE_GIFT_ASSET_SYNC`. Autres écarts hérités dans les appels réseau, erreurs et choix de carte primaire, décrits ci-dessous. |
| `deploy/Laboutik/source_templates/login.html` → `webview/templates/login.html` | Lien d'accès aux sources. |
| `deploy/Laboutik/source_templates/kiosk_base.html` → `htmxview/templates/kiosk/base.html` | Lien d'accès aux sources. |
| `deploy/Laboutik/source_templates/infos.html` → `htmxview/templates/appsettings/infos.html` | Lien d'accès aux sources. |
| `deploy/source/admin-templates/admin/base_site.html` → `source_templates/admin/base_site.html` dans Fedow et Laboutik | Template partagé ajoutant un lien AGPL dans l'administration Django. |

En complément, `deploy/Laboutik/nginx/laboutique.conf` ajoute l'alias `/admin` → `/adminstaff/` demandé pour Aix. Les configurations Nginx de Fedow, Laboutik et Lespass exposent `/source/`. Ce sont des configurations web autour des applications, pas des règles de paiement.

## Écarts importants dont le pourquoi n'est pas établi

Le montage d'une ancienne copie complète peut supprimer des corrections contenues dans l'image de référence. Il ne suffit donc pas de regarder les fonctions que nous voulions ajouter.

1. **Fedow, `serializers.py`** : le remplacement retire le bloc atomique explicite qui groupe `CREATION` et `REFILL`, l'association explicite `creation_associee`, des protections de concurrence/retry et la garde `self.checkout_stripe and` sur le contrôle de doublon. Il retire également la prise en charge d'assets archivés lors d'une fusion de portefeuille et remet `primary_places.clear()` pour un VOID, au lieu de retirer seulement le lieu demandeur. Certains mécanismes de retry/lock sont spécifiques à SQLite alors que notre configuration utilise PostgreSQL ; l'écart ne prouve donc pas à lui seul un bug identique, mais les règles de transaction et de fusion doivent être revues séparément. Aucune justification trouvée pour ces régressions de contenu.
2. **Laboutik, `fedow_api.py`** : les appels `_get`/`_post` ne conservent pas les timeouts réseau présents dans la source de l'image. En cas de lenteur Fedow, le code ne borne plus ces attentes de la même manière. Les modifications amont sur le choix de carte primaire, la gestion d'erreur d'adhésion et certains cas de cartes déjà créées ne sont pas conservées.
3. **Laboutik, `views.py`** : la copie ne conserve pas `Commande.methode_BI` pour la vente de billets en caisse et les enrichissements de vérification des adhésions Lespass présents dans la référence. Elle tente aussi un enregistrement de carte pour toute exception de consultation Fedow, ce qui confond potentiellement une carte inconnue avec une panne de connexion.
4. **Fedow, dashboard** : l'ancienne vue de suivi remplace la vue amont et fait disparaître plusieurs calculs du dashboard réseau (dormance, masse monétaire, etc.). Les filtres de suivi conservent des noms de bars historiques.

Ce sont des constats de comparaison statique, pas des incidents financiers reproduits. Aucun paiement, remboursement, débit de portefeuille ou essai de vente n'a été exécuté. Pour corriger, il faut reprendre les personnalisations minimales sur les sources épinglées et tester les parcours concernés ; une restauration automatique des fichiers entiers ne serait pas une correction suffisamment étudiée.

## Fichiers complémentaires hors logique métier

- Construction : `dockerfile` (Python 3.11 Debian Bookworm, installation APT regroupée et nettoyage), `.dockerignore` (exclut contexte local, venv et sorties de sources), `.gitignore` (état Terraform, secrets/runtime et exceptions pour les consignes partagées).
- Documentation/crédits : `AUTHORS.md`, `README.md`, nouveau `NOTICE.md`.
- Consignes des agents, ajoutées : `.claude/CLAUDE.md`, `.claude/NOTES.md`, `.claude/OBJECTIFS.md` ; elles ne sont pas du code exécuté par TiBillet.
- Tests ajoutés : `tests/pytest/test_qr_card_onboarding.py`, `test_qr_card_fedow_e2e.py`, `test_configure_gala_apex.py`, `test_configure_gala_refill.py`, `test_fedow_local_transport.py`. Ils vérifient QR, domaines, bouton et réseau ; l'E2E utilise Stripe test et un backend sans email sortant. Leur existence ne couvre pas tous les écarts des anciennes surcharges.
- Le reste de la pipeline/IaC/runtime, les manifestes et les archives historiques sont séparés dans `all-files.tsv`. Une archive ajoutée ne signifie pas que son code est chargé par l'application. `deploy/Laboutik_100-jours-225/` et `deploy/Lespass/legacy-100j-qr-flow/` ne sont pas la stack active Aix auditée ici.

## Refaire les comparaisons sans modifier le serveur

Depuis la racine du dépôt :

```sh
# Toute la différence avec le contenu initial du fork :
git diff --name-status f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9 origin/main

# Code applicatif Lespass seulement :
git diff f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9 origin/main -- Administration AuthBillet BaseBillet TiBillet fedow_connect seo

# Histoire récente d'un fichier, en restant sur la lignée du fork :
git log --first-parent --oneline f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9..origin/main -- BaseBillet/views_qr_card.py

# Les gros fichiers métier importés ont-ils été retouchés après l'import ?
git diff bc5b1a85a59872faf885c3916698042abe91f0d0 origin/main -- deploy/Fedow/custom_patches/fedow_core/serializers.py deploy/Laboutik/views.py deploy/Laboutik/validators.py deploy/Laboutik/fedow_api.py
```

Pour Fedow/Laboutik, lire `overlays.json` et les fichiers `.diff` de ce dossier : ils comparent les fichiers réellement montés aux mêmes versions sources que les images épinglées, pas à une branche amont mouvante. `lespass-application.diff` et `lespass-build.diff` sont les différences Lespass complètes. Ces preuves restent locales dans `.context/`, sans changement du code applicatif.
