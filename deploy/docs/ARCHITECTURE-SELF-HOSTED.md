# Architecture cible : hébergement auto-géré (Proxmox)

Statut : **plan, 24 octobre 2026. Rien n'est implémenté ni déployé.** Il remplace
le plan « une VM et une pipeline par gala » (supprimé avec la branche
`local_hosted`). Les décisions viennent de la discussion du 22–24 octobre.

## 1. Décisions retenues

| Sujet | Décision |
|---|---|
| Paiement | **CAWL uniquement** sur cette architecture. Stripe reste sur `main` / AWS. |
| Instances | **4 VM Linux** (Docker Compose) : `galas-test`, `galas-prod`, `kfet-test`, `kfet-prod`. Créées à la main par l'administrateur Proxmox. |
| Un événement | Un **tenant Lespass** dans l'instance (créé par le wizard `onboard`), pas une VM. |
| Monnaie | **Une monnaie par édition** (comptabilité propre). Jamais partagée entre éditions. |
| Images | Construites **une fois** par GitHub Actions, publiées sur **GHCR**, déployées par digest : l'image testée est celle de production. |
| Secrets | **Sur l'instance**, hors git et hors image (voir §6). Pas de SOPS, pas d'Infisical. |
| Code | **Minimum de code ajouté** : on réutilise ce que TiBillet prévoit (tenants, wizard, lieux et monnaies Fedow). |
| Branches | `main` = filet de sécurité Stripe pour le gala du mois prochain, **intact**. `migration/cawl-payments` est la future `main` (fusion après le gala). |
| Sauvegardes | Jamais sans accord ponctuel de l'utilisateur. |
| AWS | Reste en service tant que le gala du mois prochain n'est pas passé. Aucune bascule avant validation complète. |

## 2. Audit (code lu, rien exécuté)

| Application | Plusieurs galas dans une instance ? | Preuve |
|---|---|---|
| Lespass | Oui | `django-tenants`, `TENANT_MODEL = Customers.Client`, un schéma par organisation. |
| Fedow | Oui | `Place` (portefeuille, domaine Lespass propre) et `Asset` créé par le portefeuille d'un lieu ; `Card.primary_places` est une relation multiple. |
| LaBoutik (V1, image séparée) | **Non** | `Configuration(SingletonModel)`, `MAIN_ASSET_NAME` et `LESPASS_TENANT_URL` lus dans l'environnement, pas de `django-tenants`. |
| CAWL (`PaiementCawl`) | **Non, pas encore** | `gateway()` compare `CAWL_TENANT_SCHEMA` au schéma courant : un seul tenant par instance. |

Sources lues : ce dépôt, et les archives de sources Fedow/LaBoutik de la release
`sources-gala-am-aix-native-20261010-v4` (sommes de contrôle vérifiées).

**Non vérifié** : que la création d'un tenant par le wizard crée bien le lieu et
la monnaie de l'édition côté Fedow ; l'attribution du webhook CAWL au bon tenant
(seul le début de `PaiementCawl/views.py` a été lu) ; le comportement de
`create_tenant` sans Stripe Connect (`id_acc_connect`).

## 3. Vue d'ensemble

```text
GitHub (migration/cawl-payments)
   └─ GitHub Actions : build + tests ──▶ GHCR (images, digest)
                                           │ même digest
                    ┌──────────────────────┴───────────────┐
                    ▼                                      ▼
            galas-test / kfet-test                 galas-prod / kfet-prod
        ┌────────────────────────────┐        (mêmes images, autres secrets)
        │ Traefik                    │
        │ Lespass + Celery + Postgres│  ← tenants : un par événement
        │ Fedow (lieux, monnaies)    │
        │ LaBoutik ×N (un par édition)│ ← conteneur + base par édition
        └────────────────────────────┘
        secrets : /opt/tibillet/secrets/*.env (0600), jamais écrasés par un déploiement
```

## 4. Créer un événement : automatique

1. Le wizard `onboard` existant (identité → vérification → lieu → … → lancement)
   appelle `create_tenant_from_draft` : domaine, admin, configuration, brouillons
   d'événements. Il consomme un tenant du stock `WAITING_CONFIG`.
2. Une étape « gala » à ajouter **après** cette tâche (code minimal) :
   autoriser le tenant pour CAWL, créer/relier la monnaie de l'édition dans Fedow,
   lancer le LaBoutik de l'édition, importer les cartes.

À prévoir : stock `WAITING_CONFIG` toujours approvisionné (`create_empty_tenant`) ;
domaine des galas ajouté à `DNS_CHOICES` ; DNS wildcard + certificat.

## 5. Corrections de code identifiées

| # | Changement | Pourquoi |
|---|---|---|
| 1 | CAWL : liste de tenants autorisés (`CAWL_TENANT_SCHEMAS`) à la place d'un seul ; vérifier que le webhook retrouve le tenant du paiement | Multi-gala |
| 2 | Un LaBoutik par édition : projet Compose paramétré (noms de conteneurs, base, volumes, domaine `cashless-<édition>`) | LaBoutik est mono-lieu |
| 3 | Vérifier/neutraliser le passage Stripe Connect de `create_tenant` quand `PAYMENT_PROVIDER=cawl` | Wizard sans Stripe |
| 4 | Scripts de déploiement sans AWS (registre, secrets, SSM) pour la cible Proxmox | Autonomie |
| 5 | `secrets-init` et `secrets-check` | Formalisme des secrets |
| 6 | Workflow GitHub Actions : build, tests, publication GHCR, tag de version | Images communes |

## 6. Secrets

- Dossier `/opt/tibillet/secrets/` sur chaque VM : fichiers `.env` en 0600, propriétaire dédié.
- `secrets-init` : première installation ; génère clés Django/Fernet et mots de passe
  des bases ; **refuse d'écraser** un fichier existant. Les clés CAWL sont saisies à la main.
- `secrets-check` : vérifie la présence et la non-vacuité des clés obligatoires, et
  qu'aucune clé de test n'est en production ; le déploiement s'arrête s'il échoue.
- Un déploiement **ne modifie jamais** ces fichiers.
- **Copie hors VM** (gestionnaire de mots de passe), faite une fois à la création puis
  à chaque changement. La clé Fernet de Fedow est critique : perdue, les données
  chiffrées sont irrécupérables ; jamais régénérée automatiquement.

## 7. Réseau (pfSense)

Un seul point d'entrée public par instance :

1. **NAT** (redirection de ports) sur pfSense : WAN 443 (et 80 si HTTP-01) vers l'IP
   interne de la VM (ou du reverse proxy commun). Règles de pare-feu associées.
2. Le reverse proxy route par nom de domaine vers la bonne VM.
3. Certificats : **DNS-01 via l'API OVH** (wildcard, sans ouvrir le port 80).
4. Les webhooks CAWL arrivent en HTTPS sur le même port 443 : le site doit être
   joignable depuis Internet.
5. Résolution interne (split DNS) pour que les postes du réseau local atteignent
   les noms publics.

Le guidage pas à pas dans l'interface pfSense reste à faire avec les écrans réels.

## 8. Test → production, sans toucher aux DNS

Chaque instance a ses **noms fixes** (`*-test`, `*-prod`). Ce qui passe de test à
production, ce sont les **images** (même digest), pas le trafic : il n'y a pas de
changement quotidien d'IP chez OVH. Un vrai basculement de trafic, si nécessaire,
se ferait dans le reverse proxy (changer le serveur cible d'un nom), sans modifier
les DNS ; à concevoir quand les instances tourneront.

## 9. Étapes de mise en place

1. Plan validé (ce document).
2. Corrections de code 1 à 3 sur `migration/cawl-payments`, avec tests.
3. Workflow GHCR (6) et scripts sans AWS (4, 5).
4. L'administrateur crée `galas-test` (Linux, Docker, ressources) ; je guide.
5. Installation de l'instance de test : secrets, images, tenant de gala fictif.
6. Validation : inscription, mails, import des cartes, recharge, remboursement du
   solde (sandbox CAWL), mise à jour, redémarrage.
7. Réseau pfSense et certificats ; test d'un webhook CAWL réel.
8. Instances `kfet-test`, puis les deux de production.
9. Qualification CAWL en production (petite recharge réelle puis remboursement).
10. Bascule publique **après** le gala du mois prochain, sauf validation complète.

## 10. Hors périmètre

Renouvellements automatiques, terminaux bancaires connectés, répartition des fonds
entre organisations, matériel de caisse. Voir `operations/cawl-scope-and-wallet-refunds.md`.

## 11. Points ouverts

- Version intégrée de TiBillet (Fedow et LaBoutik dans Lespass, branches V2 amont,
  non reprises ici) : décision séparée, avec son propre audit.
- Dimensionnement des VM (CPU, RAM, disque) et nombre de LaBoutik simultanés.
- Ancien plan Proxmox (rôles `TiBilletProvision`, pool `tibillet-test`) : plus
  nécessaire tant que les VM sont créées à la main ; à réutiliser si on automatise.
