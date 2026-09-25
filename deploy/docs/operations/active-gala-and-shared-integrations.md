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

## Secrets Manager

Foundation crée pour chaque gala `tibillet-gala-paris/galas/<slug>/generated`.
Après l'apply approuvé, son étape Finalize crée **une seule fois** une valeur
contenant les clés Django, les trois clés Fernet, les mots de passe PostgreSQL
et le token interne Fedow/Lespass. Une exécution ultérieure préserve
`AWSCURRENT`. Aucune valeur n'entre dans Terraform, le catalogue, Git ou les
artefacts CodePipeline.

Trois secrets communs sont créés par Terraform, sans valeur :

- `tibillet-gala-paris/shared/integrations-stripe-test`, lisible par Smoke ;
- `tibillet-gala-paris/shared/integrations-stripe-live`, lisible par les galas réels ;
- `tibillet-gala-paris/shared/integrations-mail`, lisible par tous.

L'administrateur renseigne les vrais identifiants **directement dans Secrets
Manager**, jamais dans Git ou Terraform. Chaque secret Stripe a ce schéma (ici
une clé test fictive ; le secret live a `mode: live` et des préfixes `sk_live_`
et `pk_live_`) :

```json
{
  "schema_version": 1,
  "stripe": {
    "mode": "test",
    "secret_key": "sk_test_EXAMPLE",
    "publishable_key": "pk_test_EXAMPLE",
    "fedow_webhook_secret": "whsec_EXAMPLE"
  }
}
```

Le secret mail commun a le schéma suivant (valeurs fictives) :

```json
{
  "schema_version": 1,
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
  }
}
```

Les noms de domaine communs y sont déclarés ; le runtime refuse un écart avec
les noms approuvés dans Terraform et le catalogue Foundation. Sur l'EC2, le
script runtime lit le secret généré du gala, le secret Stripe de son
environnement et le secret mail, puis construit les trois fichiers
`fedow.env`, `laboutik.env`, `lespass.env` en mode `0600`. Les domaines,
connexions interservices, noms PostgreSQL et paramètres communs sont assemblés
automatiquement. Smoke configure le backend e-mail Django « dummy » et son
groupe réseau bloque les ports SMTP sortants : aucun mail aux participants ne
part. `test_recipient` reste la destination prévue pour un futur relais de
test ; l'envoi effectif vers cette boîte n'est **pas encore implémenté**. Les
anciens conteneurs `<slug>/runtime` sont conservés comme archives vides ; les
EC2 ne les lisent plus.

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
effectue un stop/start EC2 (sans modification dans l'invité), puis exige une
adresse temporaire et SSM `Online`. Ce rattrapage concerne la migration des
anciennes EC2 ; les nouveaux galas sont créés directement avec une IPv4
temporaire et sans EIP dédiée.
