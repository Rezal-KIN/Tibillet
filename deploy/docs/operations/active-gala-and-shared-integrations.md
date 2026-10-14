# Gala actif, IP publique unique et secrets partagés

**Statut : code cible versionné, à vérifier dans AWS après l'apply.** Smoke
lit les clés Stripe test et les galas réels les clés live du même compte, dans
des secrets différents. L'EC2 Smoke ne reçoit pas le droit de lire les clés
live.

## Source de vérité

- Toutes les instances Gala restent indépendantes : EC2, bases, clés Fernet,
  clés Django et mots de passe PostgreSQL propres à chacune.
- Les noms publics sont communs : `galas-am-aix.rezal.fr`,
  `fedow.galas-am-aix.rezal.fr` et `cashless.galas-am-aix.rezal.fr`.
  `shared_public_domain` et le catalogue Foundation les fixent ; le DNS n'est
  modifié qu'une fois pour pointer vers l'IP élastique partagée.
- Smoke utilise ces mêmes noms lorsqu'il est sélectionné comme gala actif.
  La pipeline de bascule peut déplacer l'IP vers Smoke puis la remettre sur
  un gala réel ; les autres EC2 restent hors trafic public, sans être arrêtées
  par défaut, et le DNS reste inchangé après la première migration.
- Terraform conserve l'allocation de cette IP, initialement l'ancienne IP Aix.
  Il n'en gère pas l'association après la première migration. Le paramètre SSM
  `/tibillet-gala-paris/active-gala` indique quel gala détient le trafic ; seul
  le workflow manuel `...-active-gala` le modifie après vérification.
- Le groupe de sécurité HTTP/HTTPS est attaché uniquement à l'instance active.
  Les autres EC2 gardent leur accès sortant et SSM, avec une adresse publique
  temporaire attribuée par AWS après la perte de leur EIP.

## Secrets Manager : deux secrets au total

Tous les identifiants sont regroupés par environnement dans deux objets. Les
noms historiques sont conservés pour garder les mêmes ARN :

- **dev** : `tibillet-gala-paris/shared/integrations-stripe-test` ;
- **prod** : `tibillet-gala-paris/shared/integrations-stripe-live`.

Chaque objet contient Stripe, CAWL, le courrier, les domaines, l'administration
et une entrée de clés stables par gala. Les deux Smoke lisent uniquement dev.
Les galas réels et l'archive de l'ancien Aix utilisent prod. Les clés de chaque
gala restent différentes ; leur regroupement ne les régénère jamais.

Exemple de structure dev, avec des valeurs fictives et une table de galas vide
avant sa première initialisation :

```json
{
  "schema_version": 2,
  "environment": "dev",
  "stripe": {
    "mode": "test",
    "secret_key": "sk_test_EXAMPLE",
    "publishable_key": "pk_test_EXAMPLE",
    "fedow_webhook_secret": "whsec_EXAMPLE"
  },
  "cawl": {
    "mode": "test",
    "merchant_id": "",
    "api_key_id": "",
    "api_secret": "",
    "webhook_key_id": "",
    "webhook_secret": ""
  },
  "mail": {
    "host": "smtp.example.invalid",
    "port": 587,
    "username": "EXAMPLE",
    "password": "EXAMPLE",
    "from": "contact@example.invalid",
    "admin_email": "admin@example.invalid"
  },
  "test_recipient": "smoke@example.invalid",
  "site": {
    "lespass_domain": "galas-am-aix.rezal.fr",
    "fedow_domain": "fedow.galas-am-aix.rezal.fr",
    "laboutik_domain": "cashless.galas-am-aix.rezal.fr",
    "public_name": "Gala",
    "tenant_subdomain": "festival",
    "meta_subdomain": "agenda"
  },
  "admin": {
    "username": "admin",
    "password_hash": "EMPREINTE_DJANGO_PBKDF2_SHA256"
  },
  "galas": {}
}
```

Prod utilise `environment: prod` et `mode: live` dans les deux fournisseurs.
Les identifiants sont saisis directement dans Secrets Manager, jamais dans Git.
`PAYMENT_PROVIDER` sélectionne Stripe ou CAWL ; les champs CAWL vides bloquent
uniquement le démarrage CAWL. Smoke désactive les envois aux participants avec
le backend mail dummy et ses restrictions réseau.

Foundation ajoute une seule fois `galas.<slug>` : clés Django et Fernet,
mots de passe PostgreSQL et token interne Fedow/Lespass. Elle préserve une
entrée déjà présente. Une écriture concurrente du secret est détectée avec le
numéro de version `AWSCURRENT` : une autre entrée ou une modification des
identifiants externes ne peut pas être écrasée par le finaliseur.
Foundation peut lire et mettre à jour uniquement ces deux secrets pour cela.

Le runtime fait une seule lecture du secret de son environnement. Il sélectionne
les clés de son gala et produit `fedow.env`, `laboutik.env`, `lespass.env` et
`admin.json` en mode `0600`. Le courrier et l'empreinte administrateur sont dans
le même JSON ; la version séparée `GALA_ADMIN` n'est plus nécessaire. Les trois
variables de configuration historiques `GENERATED_SECRET_ARN`,
`SHARED_STRIPE_SECRET_ARN` et `SHARED_MAIL_SECRET_ARN` pointent toutes vers cet
unique ARN. Le lecteur reste compatible avec l'ancien format pendant la migration.

Avant de retirer les anciens objets, installer le nouveau lecteur sur les deux
Smoke, copier les valeurs et clés existantes dans les deux objets, puis vérifier
l'identité des fichiers Stripe et la sélection CAWL. Aucun mot de passe ou clé de
chiffrement n'est changé. La restauration de l'ancienne archive Aix utilise les
clés `galas.gala-am-aix` du secret prod et le runtime versionné actuel.

## Déploiement et bascule du trafic

1. La pipeline Test publie une image Lespass immuable et déploie la stack
   épinglée sur Smoke. Après succès, elle écrit un marqueur immuable ; la
   validation Production exige que son manifeste corresponde exactement à ce
   marqueur avant de présenter l'approbation humaine.
2. Le healthcheck Production résout les trois noms publics vers `127.0.0.1`
   sur **cette EC2**. Il ne peut pas valider par erreur le gala déjà actif.
3. Démarrer manuellement `tibillet-gala-paris-production-active-gala` avec
   `TargetGalaSlug`. Son plan liste l'instance cible, l'instance actuelle,
   l'IP et les groupes de sécurité. Revoir puis approuver.
4. L'apply vérifie que le plan est encore exact, teste localement l'EC2 cible
   via SSM, déplace l'IP et le groupe public, vérifie les trois URL en HTTPS
   avec leur certificat, puis écrit `active-gala`. En cas d'échec, il restaure
   l'association et les groupes précédents.

Le premier passage depuis Stockholm demande **une seule** modification DNS
vers l'IP Paris partagée. Il faut coordonner cette modification avec la
première activation, puis vérifier le certificat et les trois URL publiques.
Les changements de gala suivants n'exigent plus de modification DNS.

## Mise à jour des EC2 existantes

Le premier boot installe Docker, AWS CLI, SSM et le dépôt au commit approuvé.
`deploy/tools/runtime/install-runtime-contract.sh` réinstalle les scripts et
unités systemd depuis ce même dépôt, sans démarrer les applications. Il peut
être rejoué via SSM après un `git fetch` du nouveau commit. La configuration
de chaque EC2 doit alors contenir les deux ARN non secrets
`GENERATED_SECRET_ARN`, `SHARED_STRIPE_SECRET_ARN` et
`SHARED_MAIL_SECRET_ARN`.

Avant de supprimer l'ancienne EIP Smoke, le plan Terraform doit confirmer
qu'elle n'est visée par aucun DNS. Après libération, vérifier l'IPv4 temporaire
et SSM `Online`. L'EIP Aix devient l'unique adresse fixe du Gala Paris.
Si l'ancienne EC2 Smoke, lancée avec son EIP propre, ne reçoit pas d'adresse
IPv4 temporaire après cette libération, utiliser le script versionné
`deploy/tools/reconcile-inactive-gala-outbound.py` avec son ID exact et
`--gala gala-smoke`. Il refuse l'instance active, vérifie les tags Terraform,
active l'auto-attribution IPv4 sur son interface primaire (sans modification
dans l'invité). Si SSM reste hors ligne après le retour de l'IP, il redémarre
une seule fois cette EC2 inactive. Il exige ensuite une adresse temporaire et SSM
`Online`. Ce rattrapage concerne la migration des
anciennes EC2 ; les nouveaux galas sont créés directement avec une IPv4
temporaire et sans EIP dédiée.
