# Architecture cible : hébergement auto-géré (Proxmox)

Statut : **plan, 25 octobre 2026. Rien n'est implémenté ni déployé.** Il remplace
le plan « une VM et une pipeline par gala » (supprimé avec la branche
`local_hosted`) et la variante « un LaBoutik par édition » (abandonnée le
24 octobre au profit de la version intégrée).

## 1. Décisions retenues

| Sujet | Décision |
|---|---|
| Paiement | **CAWL uniquement** sur cette architecture. Stripe reste sur `main` / AWS. |
| Instances | **4 VM Linux** (Docker Compose) : `galas-test`, `galas-prod`, `kfet-test`, `kfet-prod`. Créées à la main par l'administrateur Proxmox. |
| Un événement | Un **tenant Lespass** dans l'instance (créé par le wizard `onboard`), pas une VM. |
| Caisse | **LaBoutik intégré** (app `laboutik` dans Lespass), multi-tenant par conception. |
| Monnaie | **Une monnaie par édition** (comptabilité propre). Jamais partagée entre éditions. |
| Base de code | La **version intégrée** (tag `archive/main-fedow-import`, 21 septembre 2026), à laquelle on reporte notre travail : `deploy/`, `PaiementCawl`, `payment_providers`, et une dizaine de fichiers de l'application. Décidé le 25 octobre. |
| Images | Construites **une fois** par GitHub Actions, publiées sur **GHCR**, déployées par digest : l'image testée est celle de production. |
| Secrets | **Sur l'instance**, hors git et hors image (voir §6). Pas de SOPS, pas d'Infisical. |
| Code | **Minimum de code ajouté** : on réutilise ce que TiBillet prévoit (tenants, wizard, `fedow_core`, interface PSP). |
| Branches | `main` = filet de sécurité Stripe pour le gala du mois prochain, **intact**. `migration/cawl-payments` (Fedow et LaBoutik séparés, CAWL validé) reste la référence tant que le report n'est pas validé. La branche reportée devient la future `main` après le gala. |
| Sauvegardes | Jamais sans accord ponctuel de l'utilisateur. |
| AWS | Reste en service tant que le gala du mois prochain n'est pas passé. Aucune bascule avant validation complète. |

## 2. Audit (code lu, rien exécuté en pile complète)

| Application | Plusieurs galas dans une instance ? | Preuve |
|---|---|---|
| Lespass | Oui | `django-tenants`, `TENANT_MODEL = Customers.Client`, un schéma par organisation. |
| `fedow_core` (moteur local) | Oui | `Asset.tenant_origin`, `Federation` ; règle de code : toujours filtrer par tenant. |
| `laboutik` intégré | Oui | App tenant de Lespass (`urls_tenants`), rapports, archivage fiscal. |
| Fedow « legacy » (image séparée) | Oui | `Place`, `Asset` par lieu, `Card.primary_places`. |
| LaBoutik V1 (image séparée) | **Non** | Singleton de configuration, `MAIN_ASSET_NAME` dans l'environnement. N'est pas retenu. |
| CAWL (`PaiementCawl`) | **Non, pas encore** | `gateway()` compare `CAWL_TENANT_SCHEMA` au schéma courant : un seul tenant par instance. |

### La version intégrée est un état de transition

- `fedow_core` est le moteur de portefeuille **local**. `fedow_connect/services.py` : il
  « permettra un jour de débrancher le Fedow legacy » ; `fedow_core/CARTES.md` : il
  « remplace progressivement `fedow_connect/` ».
- Aujourd'hui, **l'installation, les lieux et les cartes passent encore par le Fedow
  distant** (`root_fedow_handshake`, `FedowAPI.create_place`). La pile de développement
  de la branche lance d'ailleurs `tibillet/fedow` à côté de Lespass.
- Conséquence : deux moteurs de portefeuille coexistent. Il faut décider, pour chaque
  flux du gala, lequel fait foi (voir §11).
- Interface prévue pour ajouter un prestataire de paiement : `fedow_core/PSP_INTERFACE.md`
  (`RefillService.process_cashless_refill`) ; remboursement en espèces :
  `fedow_core/REFUND.md`.
- Les historiques de `main` et de cette branche n'ont **aucun ancêtre commun** : pas de
  merge possible, il faut reporter les changements.

**Non vérifié** : la pile complète n'a jamais été démarrée avec cette version (aucun
Docker dans la session de travail ; `install` exige un Fedow réel) ; l'attribution du
webhook CAWL au bon tenant ; le comportement de `create_tenant` sans Stripe Connect.

## 3. Vue d'ensemble

```text
GitHub (branche reportée)
   └─ GitHub Actions : build + tests ──▶ GHCR (images, digest)
                                           │ même digest
                    ┌──────────────────────┴───────────────┐
                    ▼                                      ▼
            galas-test / kfet-test                 galas-prod / kfet-prod
        ┌─────────────────────────────┐        (mêmes images, autres secrets)
        │ Traefik                     │
        │ Lespass + Celery + Postgres │  ← tenants : un par événement
        │   (fedow_core + laboutik)   │
        │ Fedow legacy (transition)   │
        └─────────────────────────────┘
        secrets : /opt/tibillet/secrets/*.env (0600), jamais écrasés par un déploiement
```

## 4. Créer un événement : automatique

1. Le wizard `onboard` existant (identité → vérification → lieu → … → lancement)
   appelle `create_tenant_from_draft` : domaine, admin, configuration, brouillons
   d'événements. Il consomme un tenant du stock `WAITING_CONFIG`.
2. Une étape « gala » à ajouter **après** cette tâche (code minimal) : autoriser le
   tenant pour CAWL, créer la monnaie de l'édition, importer les cartes.

À prévoir : stock `WAITING_CONFIG` toujours approvisionné (`create_empty_tenant`) ;
domaine des galas ajouté à `DNS_CHOICES` ; DNS wildcard + certificat.

## 5. Report du travail sur la version intégrée

| # | Étape | Remarque |
|---|---|---|
| 0 | **Mesurer la base** : démarrer la pile de la version intégrée (Lespass, Fedow, PostgreSQL, Redis, memcached, Celery) et lancer `tests/pytest` | Sans Docker dans la session de travail : faire en CI ou sur `galas-test`. Aucun report avant d'avoir cette mesure. |
| 1 | Reporter `deploy/` (199 fichiers, ajouts) et adapter ses scripts : plus d'images Fedow/LaBoutik épinglées si le moteur local suffit | Additif |
| 2 | Reporter `PaiementCawl` et `payment_providers` | Nouveaux dossiers |
| 3 | Réconcilier une dizaine de fichiers communs : `BaseBillet/{tasks,urls,views}.py`, `TiBillet/settings.py`, `Administration/admin/{site,dashboard}.py`, `AuthBillet/utils.py`, `fedow_connect/fedow_api.py`, `dockerfile`, `.dockerignore`, `.gitignore` | Conflits attendus, un par un |
| 4 | Brancher la recharge et le remboursement CAWL sur `fedow_core` (`RefillService`, `rembourser_en_especes`) au lieu de l'API du Fedow distant | Reprendre nos tests de référence |
| 5 | CAWL multi-tenant : liste de tenants autorisés (`CAWL_TENANT_SCHEMAS`), webhook retrouvant le bon tenant | Voir §2 |
| 6 | Spécificités du gala : cartes QR, import des 7 020 cartes, mails, rapports | À revalider une à une |
| 7 | Neutraliser le passage Stripe Connect de `create_tenant` quand `PAYMENT_PROVIDER=cawl` | Wizard sans Stripe |

## 6. Secrets

- Dossier `/opt/tibillet/secrets/` sur chaque VM : fichiers `.env` en 0600, propriétaire dédié.
- `secrets-init` : première installation ; génère clés Django/Fernet et mots de passe
  des bases ; **refuse d'écraser** un fichier existant. Les clés CAWL sont saisies à la main.
- `secrets-check` : vérifie la présence et la non-vacuité des clés obligatoires, et
  qu'aucune clé de test n'est en production ; le déploiement s'arrête s'il échoue.
- Un déploiement **ne modifie jamais** ces fichiers.
- **Copie hors VM** (gestionnaire de mots de passe), faite une fois à la création puis
  à chaque changement. La clé Fernet est critique : perdue, les données chiffrées sont
  irrécupérables ; jamais régénérée automatiquement.

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

## 9. Installation refaisable et protocoles de test

Il n'existe aujourd'hui **aucun workflow GitHub Actions** dans le dépôt, mais de nombreux
tests (`tests/pytest`, 261 fichiers dans la version intégrée ; `tests/e2e` Playwright).

- **Script d'installation idempotent** : secrets, migrations, tenants, import des cartes ;
  le relancer après une mise à jour d'image ne casse rien.
- **Script `test-stack`**, identique en local et en CI : démarrage de la pile, migrations,
  création d'un tenant par le wizard, paiement CAWL simulé, relance de l'installation,
  mise à jour depuis l'image précédente.
- **Workflow GitHub Actions** : à chaque nouvelle image, tests unitaires puis `test-stack`.
  Gratuit sur un dépôt public. La pipeline AWS reste séparée.

## 10. Étapes de mise en place

1. Plan validé (ce document).
2. Mesurer la base de la version intégrée (§5, étape 0) en CI ou sur `galas-test`.
3. Report par étapes (§5, étapes 1 à 7), avec les tests à chaque étape.
4. Workflow GHCR, scripts sans AWS, secrets (`secrets-init`, `secrets-check`).
5. L'administrateur crée `galas-test` (Linux, Docker, ressources) ; je guide.
6. Installation de l'instance de test : secrets, images, tenant de gala fictif.
7. Validation : inscription, mails, import des cartes, recharge, remboursement du
   solde (sandbox CAWL), mise à jour, redémarrage.
8. Réseau pfSense et certificats ; test d'un webhook CAWL réel.
9. Instances `kfet-test`, puis les deux de production.
10. Qualification CAWL en production (petite recharge réelle puis remboursement).
11. Bascule publique **après** le gala du mois prochain, sauf validation complète.

## 11. Hors périmètre et points ouverts

Hors périmètre : renouvellements automatiques, terminaux bancaires connectés,
répartition des fonds entre organisations, matériel de caisse. Voir
`operations/cawl-scope-and-wallet-refunds.md`.

Points ouverts :

- **Deux moteurs de portefeuille** : pour le gala, les cartes et soldes sont-ils dans le
  Fedow distant ou dans `fedow_core` ? Quel flux crédite quel moteur ?
- Dimensionnement des VM (CPU, RAM, disque) et ressources du Fedow legacy.
- Avancement de TiBillet sur le débranchement du Fedow legacy (hors de ce dépôt).
- Ancien plan Proxmox (rôles `TiBilletProvision`, pool `tibillet-test`) : plus nécessaire
  tant que les VM sont créées à la main.
