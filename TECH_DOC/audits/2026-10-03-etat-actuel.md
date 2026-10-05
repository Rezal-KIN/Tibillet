# Différences actuelles avec TiBillet après les retraits C/D/F/G

Inventaire du code local au commit `717021e1`,
référence complète dans le JSON de preuves. Aucun changement applicatif dans cet
inventaire. Les retraits/corrections locaux ne sont pas déployés par ce travail.
L'état d'un serveur en service n'est pas déduit de cet inventaire.

## Références fixes

- Lespass initial au fork : `TiBillet/Lespass@fd7680891c31bbdf6215e7a0750074de89ff5e8e`.
  Son contenu est celui de `f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9` dans
  l'historique réécrit du fork (même arbre Git).
- Fedow : référence de l'image épinglée,
  `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c`.
- LaBoutik : référence de l'image épinglée,
  `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`.

Ce n'est pas une comparaison avec les branches `main` amont d'aujourd'hui.
Les archives Fedow/LaBoutik sont vérifiées par SHA-256 contre le catalogue
`deploy/source/image-sources.json` avant la comparaison des sources montées.

Preuves : [JSON complet](2026-10-03-etat-actuel-preuves.json),
[liste exhaustive des fichiers Git](2026-10-03-etat-actuel-fichiers.tsv).
Le snapshot initial `2026-10-03-fork/` reste intact.

## Lespass — 16 fichiers applicatifs différents

Dix fichiers existants modifiés et six fichiers ajoutés : 492 lignes ajoutées et
24 supprimées. Ces fichiers sont construits dans l'image ; aucun montage de code
Python Lespass ne les remplace. Ils n'ont pas changé depuis l'audit initial.

| Fichier | Différence restante et raison |
| --- | --- |
| `BaseBillet/views_qr_card.py` | Ajout A : inscription/connexion par QR, liaison carte/portefeuille, retour vers la carte ; preuve email requise pour un compte existant |
| `BaseBillet/urls.py` | Routes A `/qr/link/`, `/qr/check-email/<uuid>/`, `/qr/<uuid>/` |
| `AuthBillet/utils.py` | Email personnalisable et option retournant utilisateur + indicateur de création, nécessaires à A |
| `BaseBillet/tasks.py` | Retrait des liens de connexion complets dans les logs |
| `BaseBillet/templates/reunion/views/register.html` | Texte de recharge, jeton CSRF et retrait de logs navigateur d'email |
| `BaseBillet/templates/reunion/views/qr_landing.html` | Page carte liée, bouton recharge existant, accès compte |
| `BaseBillet/templates/reunion/views/qr_check_email.html` | Page de confirmation par lien email |
| `BaseBillet/templates/emails/qr_connexion.html` | Email du parcours carte |
| `BaseBillet/templates/reunion/views/home.html` | B : guide cashless en trois étapes, bouton adhésion/connexion |
| `Administration/management/commands/configure_gala_apex.py` | Associer le domaine public au tenant Gala attendu |
| `Administration/management/commands/configure_gala_refill.py` | Régler le bouton de recharge Fedow/Stripe via le champ natif `force_show_refill_button` |
| `fedow_connect/fedow_api.py` | Transport Docker local vers Fedow sous `GALA_LOCAL_FEDOW=1`, avec Host public et signatures conservés |
| `TiBillet/settings.py` | Interprétation correcte des booléens SMTP TLS/SSL et backend email configurable |
| `Administration/admin/site.py` | Connexion admin par mot de passe sous `GALA_APEX_TENANT=1`, connexion mail dans les autres cas |
| `Administration/admin/dashboard.py` | K : lien des sources dans l'administration |
| `seo/templates/seo/partials/tibillet_community_links.html` | K : lien public des sources |

## Fedow — huit cibles source encore différentes

Sept fichiers montés individuellement et un template ajouté via le répertoire
partagé `source_templates`. G a disparu : le serializer des transactions est
celui de l'image native, sans copie ni montage de remplacement.

| Source locale | Cible interne | Différence restante |
| --- | --- | --- |
| `deploy/Fedow/settings.py` | `fedowallet_django/settings.py` | I : PostgreSQL au lieu de SQLite, hôtes/CSRF adaptés, répertoire templates ; browser reload réactivé en DEBUG seulement |
| `deploy/Fedow/custom_patches/fedow_dashboard/views.py` | `fedow_dashboard/views.py` | H : suivi Gala, filtres et séries ; anciennes vues remplaçant aussi les calculs du dashboard réseau natif |
| `deploy/Fedow/custom_patches/fedow_dashboard/urls.py` | `fedow_dashboard/urls.py` | H : routes suivi HTML/JSON et remplacement des routes de dashboard natif |
| `deploy/Fedow/custom_patches/fedow_dashboard/index.html` | `fedow_dashboard/templates/index/index.html` | H : accueil simplifié et accès au suivi financier |
| `deploy/Fedow/custom_patches/fedow_dashboard/suivi.html` | `fedow_dashboard/templates/index/suivi.html` | H : interface de graphiques/filtres et rafraîchissement |
| `deploy/Fedow/custom_patches/fedow_dashboard/base.html` | `fedow_dashboard/templates/base.html` | K : lien des sources dans le footer |
| `deploy/Fedow/custom_patches/fedow_dashboard/public_index.html` | `fedow_dashboard/templates/index.html` | K : lien des sources sur l'accueil public |
| `deploy/source/admin-templates/admin/base_site.html` | `source_templates/admin/base_site.html` | K : extension du template admin avec lien des sources |

H garde les libellés historiques `PIAN'S`, `oenol'ss` et `shots`. Les fonctions
de dormance, masse monétaire, pouls réseau et cycles de vie de la référence sont
toujours absentes de la copie. Les erreurs de filtre, données périmées à l'écran,
coût des requêtes et protections d'accès sont documentés dans
[la suite G/E/K/H](2026-10-03-suite-G-E-K-H.md) ; aucune refonte H n'est appliquée.

## LaBoutik — neuf cibles source encore différentes

Huit fichiers montés individuellement et le même template admin partagé que
Fedow. Trois déclarations de montage Python sont encore dupliquées dans Compose ;
elles ne correspondent pas à une seconde implémentation.

| Source locale | Cible interne | Différence restante |
| --- | --- | --- |
| `deploy/Laboutik/settings.py` | `Cashless/settings.py` | I : booléens SMTP corrigés, backend email configurable, recherche des templates sources |
| `deploy/Laboutik/install.py` | `administration/management/commands/install.py` | J : installation reprenable, conserve les appairages et évite les doublons |
| `deploy/Laboutik/views.py` | `webview/views.py` | E : enregistrement sur vraie carte introuvable ; écarts historiques de billets/adhésions encore présents |
| `deploy/Laboutik/validators.py` | `webview/validators.py` | E : validation avec enregistrement sur 404 uniquement et erreur visible ; seul écart fonctionnel de méthode restant dans ce fichier |
| `deploy/Laboutik/fedow_api.py` | `fedow_connect/fedow_api.py` | Écarts API historiques décrits ci-dessous ; synchronisation F et timeouts GET/POST revenus exactement à la référence |
| `deploy/Laboutik/source_templates/login.html` | `webview/templates/login.html` | K : lien des sources |
| `deploy/Laboutik/source_templates/kiosk_base.html` | `htmxview/templates/kiosk/base.html` | K : lien des sources |
| `deploy/Laboutik/source_templates/infos.html` | `htmxview/templates/appsettings/infos.html` | K : lien des sources |
| `deploy/source/admin-templates/admin/base_site.html` | `source_templates/admin/base_site.html` | K : lien admin des sources |

### Écarts hérités encore présents, distincts de E

Ce sont des différences de contenu avec la référence, pas des fonctionnalités
que l'utilisateur a demandé de conserver ni des incidents de production établis.

- `Commande.methode_BI` est toujours absente : la copie ne conserve pas la vente
  de billets prévue par la référence. Son dispatcher ne trouve pas cette méthode.
- `check_carte` et `Commande.methode_VT` n'interrogent pas Lespass pour enrichir
  l'affichage/la réponse avec la validité réelle des adhésions quand l'option
  native correspondante est activée.
- `Commande.methode_AD` et `NFCCard.badge` choisissent la première carte du
  responsable au lieu de la carte primaire prévue par la référence ; le traitement
  des erreurs d'adhésion de `methode_AD` diffère aussi.
- `Subscription.create_sub` retourne encore un code HTTP ou des erreurs sur
  échec au lieu de lever l'exception native attendue par l'appelant.
- `NFCCard.create` accepte 201/409, mais ne conserve pas la tolérance native du
  400 d'unicité `first_tag_id` pour les cartes déjà présentes après réinitialisation
  locale. Aucun flush de base n'a été exécuté par cet inventaire.
- `NFCCard.retrieve` écrit encore les 404 dans les logs d'erreur ; upstream traite
  ce cas normal sans ce bruit. Le type `FileNotFoundError` est conservé.
- `Transaction.refill_wallet` et `Transaction.to_place` transmettent un entier
  dans `NotAcceptable.code`, upstream une chaîne. Écart établi, sans incident
  attribué à ce seul changement de type.

Les imports et notices/commentaires ont aussi des différences sans règle métier
nouvelle. Le JSON fournit la liste AST complète des méthodes différentes.

## Configuration web et ajouts de plateforme

| Groupe | Différence avec le dépôt initial |
| --- | --- |
| L — Nginx/Traefik | Configuration des domaines Gala, proxy HTTP/WebSockets, statiques/médias, `/source/` et alias LaBoutik `/admin` vers `/adminstaff/` |
| Images/Compose | Images de release épinglées ; environnements matérialisés ; réseaux locaux et résolution des domaines vers l'hôte Gala ; persistance des données |
| AWS/Terraform | EC2 par Gala, Paris, réseau/IAM, registre des galas, IP active, S3, Secrets Manager, budgets et infrastructure de livraison |
| Pipeline | CodeBuild/CodePipeline, image Lespass, ECR, manifests immuables, tests/smoke, promotion et bascule de Gala |
| Exploitation | Préflight, initialisation, réglages QR/recharge/admin et webhook, healthchecks, sauvegarde/restauration, démarrage systemd, swap et gestion d'espace |
| K — Sources | Archives originales vérifiées, application des sources montées, publication GitHub et contrôle de disponibilité avant/après déploiement |
| Outils/archives | Scripts historiques sous `deploy/tools/scripts/`, anciennes copies 100J/Lespass ; leur présence ne prouve pas leur exécution dans la stack active |

La liste Git contient 197 fichiers sous `deploy/`, incluant code actif,
configuration, tests, documentation et archives. Ils ne représentent pas 197
modifications métier de TiBillet. Le diff total au commit examiné contient 292
fichiers, dont 51 documents/preuves sous `TECH_DOC/` et 14 manifestes `releases/`.
Les trois fichiers du présent inventaire s'ajoutent ensuite comme documentation.

Les quatre Compose actifs déclarent maintenant **46 montages distincts par
service, 49 déclarations brutes**, contre 47/50 dans l'audit initial. Seul le
montage du serializer G a disparu. C/D/F ont été retirés des fonctions mais
leurs fichiers partagés restent montés pour E et les autres écarts.
Les montages de base, médias, journaux, sauvegardes et certificats sont recensés
dans le JSON ; ils n'ont pas été retirés.

## Construction, documentation et tests

- `dockerfile` : Python 3.11 Debian Bookworm au lieu de Bullseye, installation
  APT regroupée et nettoyée ; pas de changement de dépendances Poetry.
- `.dockerignore`/`.gitignore` : exclusions du contexte local, sources générées,
  secrets/état runtime et Terraform ; consignes partagées `.claude/` versionnées.
- `AUTHORS.md`, `NOTICE.md`, `README.md`, `.claude/` et les dossiers d'audit :
  documentation, crédits et traces des décisions.
- Cinq tests Lespass ajoutés (QR, transport, domaine, bouton recharge), plus les
  tests de déploiement/corrections sous `deploy/tests/`.
- La source LaBoutik de l'image comporte déjà l'écart de construction documenté
  `docker_push_update.sh` (`VERSION=1.4` vers `1.7`). Il est enregistré comme
  provenance de l'image dans le catalogue, pas comme une nouvelle règle Gala.

## Retiré ou inchangé

- C : happy hour retiré, prix/validation TiBillet restaurés.
- D : limite de deux terminaux et exemption admin retirées.
- F : option `ENABLE_GIFT_ASSET_SYNC` retirée, synchronisation native retrouvée.
- G : réparations automatiques et ancien serializer retirés ; protections natives
  de recharge/fusion/VOID reprises directement depuis l'image.
- E : reste une personnalisation volontaire, avec correction limitée en `717021e1`.
- Modèles Lespass, migrations, `BaseBillet/views.py`, template de solde,
  `pyproject.toml` et `poetry.lock` : inchangés depuis la base du fork.
- Demande de remboursement hors Stripe/IBAN des 100J : toujours non portée dans
  Lespass actif. C'est un ajout historique absent, pas un retrait de TiBillet natif.

Vérification de cet inventaire : nouveau diff Git, comparaison des 17 cibles
source aux archives vérifiées, comparaison AST des méthodes, recomptage des
montages et vérificateur des sept unités restaurées + serializer natif. Aucun
nouveau test de vente, paiement, remboursement ou accès serveur n'a été lancé.
