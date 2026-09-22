# Archive du parcours QR / connexion — 100 jours 2026

> **Archive de référence, non intégrée.**
>
> Ce dossier conserve le code et les templates tels qu'ils étaient sur l'ancienne EC2
> `Tibillet100J_OG` le 2026-09-22. Il n'est ni importé, ni monté dans un conteneur, ni utilisé
> par la stack Lespass V2 actuelle. Ne pas ajouter ce dossier à un Compose, ne pas le copier dans
> `Lespass/app`, et ne pas le charger par un import Python. Son objectif est de préserver le
> comportement métier avant sa réimplémentation explicite contre V2.

## Provenance vérifiée

| Élément | Valeur |
| --- | --- |
| Machine source | EC2 `Tibillet100J_OG` (`i-01107b29b967dc1dc`) |
| Checkout source | `/home/ubuntu/TiBillet` |
| Remote source | `Rezal-KIN/Gala-am-Aix-Tibillet` |
| Branche / HEAD source | `main` / `ed86ee88693600462c63994f084e47c25240aa89` |
| État de la source | 7 fichiers modifiés non commités, dont ce parcours QR |
| Méthode | lecture SSH seule ; aucun fichier de secret, `.env`, dump ou `acme.json` lu ou copié |

Les fichiers sous `source/` sont des copies de contenu, à la date de l'inventaire. Ils ne sont
pas un patch applicable : l'ancienne stack emploie Lespass V1 (image Docker Hub et overlays
`custom_patches/`), alors que `deploy/Lespass/` emploie le monorepo V2 dans le submodule `app/`.

## Ce que faisait le parcours

Le point d'entrée est `GET /qr/<uuid>/`, destiné au QR code physique d'une carte NFC.

```text
scan QR /qr/<uuid>/
        |
        v
qr_card_landing()
        |
        +-- navigateur authentifié ----------------------------------------------+
        |                                                                         |
        |       affiche « Carte liée ! » (`qr_landing.html`)                      |
        |       -> Recharger ma carte (Stripe)                                   |
        |       -> Accéder à mon espace                                           |
        |                                                                         |
        +-- carte NFC éphémère / jamais liée ------------------------------------+
        |                                                                         |
        |       affiche le formulaire `register.html`                             |
        |       email + confirmation + prénom/nom selon la configuration          |
        |       POST /qr/link/                                                    |
        |                 |                                                       |
        |                 v                                                       |
        |       qr_card_link() : crée/récupère le compte, lie la carte,           |
        |       ouvre la session Django directement, puis redirige vers           |
        |       /qr/<uuid>/                                                       |
        |                                                                         |
        +-- carte déjà liée, navigateur non authentifié -------------------------+
                envoie un magic link par email et affiche
                `qr_check_email.html`; après clic dans le mail, retour vers
                /qr/<uuid>/ puis page « Carte liée ! »
```

Le comportement important est la **connexion directe uniquement lors de la première liaison
d'une carte éphémère** : l'utilisateur saisit ses coordonnées une seule fois, la carte est liée
à son wallet et la session Django est ouverte sans devoir cliquer sur un email. Une carte déjà
liée conserve au contraire le mécanisme de magic link par email.

## Fichiers conservés

| Copie archivée | Rôle dans le parcours |
| --- | --- |
| `source/Lespass/custom_patches/BaseBillet/views_balance_total.py` | Contient `qr_card_landing` et `qr_card_link`, ainsi que les vues solde/remboursement associées à l'expérience de carte. |
| `source/Lespass/custom_patches/BaseBillet/urls.py` | Déclare `qr/<uuid:pk>/` et `qr/link/`; la route `qr/link/` doit rester avant le router DRF lors d'un futur portage. |
| `source/Lespass/custom_patches/BaseBillet/templates/reunion/views/register.html` | Page d'inscription et de première liaison de carte. |
| `source/Lespass/custom_patches/BaseBillet/templates/reunion/views/qr_landing.html` | Page post-connexion « Carte liée ! » avec accès au rechargement et à l'espace personnel. |
| `source/Lespass/custom_patches/BaseBillet/templates/reunion/views/qr_check_email.html` | Page d'attente du magic link pour une carte déjà liée. |
| `source/Lespass/custom_patches/BaseBillet/templates/emails/{base,connexion}.html` | Gabarit et contenu de l'email de magic link utilisé lorsqu'une carte déjà liée est scannée hors session. |
| `source/Lespass/custom_patches/BaseBillet/views.py` | Contexte V1 complet : intégration du QR, session, compte, paiement et contrôles de droits. Il est conservé pour comprendre les appels autour du flow, pas pour être monté tel quel. |
| `source/Lespass/docker-compose.yml` | Preuve de l'ancienne architecture : image V1 et montages des `custom_patches/`, y compris les fichiers ci-dessus. Ne pas remplacer le Compose V2 actuel avec ce fichier. |

## Contrat fonctionnel à préserver lors du futur portage

1. Une URL QR valide correspond à une carte connue côté Fedow.
2. Une carte éphémère non liée affiche le formulaire de liaison, plutôt qu'un flow de connexion
   générique.
3. Après un formulaire valide, la carte est liée au wallet du compte et la personne est connectée
   dans le même navigateur avant le retour vers la page QR.
4. Une personne qui possède déjà une autre carte liée ne peut pas lier silencieusement une seconde
   carte.
5. Une carte déjà liée ne donne pas accès au compte sur la seule possession du QR : elle déclenche
   un magic link vers l'adresse déjà associée au wallet.
6. La page finale offre les accès « Recharger ma carte » et « Accéder à mon espace ».
7. Les erreurs Fedow, les UUID QR invalides et les liaisons impossibles sont traités sans exposer
   les données d'un autre compte.

## Garde-fous de sécurité pour le futur portage

- Le flow touche à l'authentification, aux wallets cashless et au rechargement Stripe : ne pas le
  réintroduire comme un simple copier-coller V1 → V2.
- Vérifier les permissions, les modèles et l'API Fedow de V2 avant de choisir les équivalents de
  `FedowAPI`, `get_or_create_user`, `django_login` et `linkwallet_cardqrcode`.
- Préserver le contrôle « une carte déjà liée ne peut pas être revendiquée par un autre compte ».
- Conserver le magic link pour une carte déjà liée ; la connexion directe est réservée au premier
  rattachement d'une carte éphémère.
- Ne jamais mettre de clé Stripe, token Fedow, identifiant de base de données ou valeur de `.env`
  dans cet archive ou dans un futur client de carte.
- Écrire des tests d'intégration sur un tenant et des wallets/cartes de test avant toute activation
  publique.

## Vérification proposée après un portage V2

1. Carte de test neuve → `/qr/<uuid>/` → formulaire → inscription → liaison wallet → session
   active → page « Carte liée ! » sans email.
2. Même carte dans un navigateur déconnecté → page d'attente + magic link → retour sécurisé sur
   la landing page après clic.
3. Carte liée à un autre compte → refus de liaison, sans révéler ses informations.
4. Compte ayant déjà une carte → tentative de seconde liaison refusée.
5. Contrôles de non-régression du solde, du rechargement Stripe et de l'accès à l'espace
   personnel.

Pour l'inventaire complet de l'ancienne EC2 et les autres personnalisations, voir
`deploy/docs/platform/tibillet100j-customizations-inventory.md`.
