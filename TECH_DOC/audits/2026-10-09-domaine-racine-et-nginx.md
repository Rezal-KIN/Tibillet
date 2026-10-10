# Domaine racine et Nginx — investigation du 9 octobre 2026

## Conclusion

Le domaine racine est correctement associé au tenant Gala sur Smoke. Il utilise le modèle natif `Customers.Domain` de TiBillet/django-tenants, avec transmission du `Host` d'origine jusqu'à Django. Les gardes de domaine passent et le domaine de retour stocké dans Fedow est le même. Aucun problème de sélection du tenant n'a été observé sur ce chemin.

L'investigation a cependant trouvé **un défaut confirmé de connectivité Celery → Fedow**, des communications qui restent dirigées vers l'EC2 publique active, et des domaines présents dans Django mais non routés par Traefik. Ces sujets appartiennent à notre adaptation de déploiement et doivent être distingués de l'utilisation du domaine racine.

Périmètre : EC2 Smoke `i-0037b98572fccdff2`, IP publique `51.44.90.200`, configuration réellement chargée et endpoints HTTPS. L'ancienne EC2 Aix `i-0801aa8a2273838aa` reste déconnectée de SSM et n'a pas été inspectée de l'intérieur. Aucun service redémarré, aucune règle appliquée, aucun appel de transaction ou modification de domaine. Les preuves privées restent dans `.context/nginx-root-investigation-20261009/` ; les résultats sans secrets figurent dans `2026-10-09-domaine-racine-et-nginx-preuves.json`.

## 1. Le domaine racine est une configuration native cohérente

La chaîne inspectée est :

```text
galas-am-aix.rezal.fr
  → Traefik : règle Host exacte
  → lespass_nginx : Host transmis sans remplacement
  → TenantMainMiddleware : recherche dans Customers.Domain
  → tenant festival
```

Le fait de choisir un tenant via son domaine et son domaine principal est le mécanisme [documenté par django-tenants](https://django-tenants.readthedocs.io/en/latest/use.html#creating-a-tenant). La commande ajoutée `configure_gala_apex` configure ce mécanisme ; elle ne remplace pas le middleware ni le moteur de base.

| Domaine enregistré | Tenant | Principal ? | Entrée Traefik effective |
| --- | --- | --- | --- |
| `galas-am-aix.rezal.fr` | `festival` | Oui | Oui, HTTP 200 |
| `festival.galas-am-aix.rezal.fr` | `festival` | Non | Non, HTTP 404 |
| `www.galas-am-aix.rezal.fr` | `public` | Oui | Non, HTTP 404 |
| `agenda.galas-am-aix.rezal.fr` | `meta` | Oui | Non, HTTP 404 |
| `m.galas-am-aix.rezal.fr` | `meta` | Non | Non, aucune règle déclarée ; pas de requête distincte effectuée |

La commande prend un verrou sur les Domain attendus, refuse un propriétaire de domaine inattendu et applique les changements dans une transaction. `configure_gala_apex --check` réussit. Le cache du domaine canonique de `festival` contient aussi l'apex actuel. Le `Place.lespass_domain` Fedow vaut cet apex : aucun ancien sous-domaine n'est encore enregistré pour ce lieu.

Les cookies de session et CSRF restent limités à l'hôte (`SESSION_COOKIE_DOMAIN=None`, `CSRF_COOKIE_DOMAIN=None`). `USE_X_FORWARDED_HOST=False`. Une requête publique avec des en-têtes `X-Forwarded-Host` et `X-Forwarded-Proto` inventés rend toujours la page canonique HTTPS correcte. Ce contrôle est ciblé, pas un audit complet de sécurité.

Le choix de l'apex conserve les URLs Gala imprimées. Revenir au sous-domaine du guide nécessiterait de préserver leur routage/redirection, sous peine de casser ces liens. Ce choix n'est pas nécessaire pour réparer les défauts ci-dessous.

## 2. Défaut confirmé : Celery ne peut pas joindre son endpoint Fedow configuré

Lespass web et son worker utilisent le même `GALA_LOCAL_FEDOW=1`, donc le client sélectionne `http://fedow_nginx` dans les deux conteneurs. Seul le conteneur web a été ajouté au réseau Docker partagé `frontend`, au commit `ed5cb0c6` du 26 septembre. Le worker est resté sur `lespass_backend`.

| Départ | Destination testée | Résultat |
| --- | --- | --- |
| Lespass web | `http://fedow_nginx/helloworld/` | Résolution locale `172.18.0.3`, HTTP 200 |
| Celery Lespass | Même adresse | **Échec de résolution DNS : `gaierror`** |
| Lespass web | Nom HTTPS Fedow, résolu par `host-gateway` | HTTP 200, certificat vérifié |
| Celery Lespass | Même nom HTTPS via `host-gateway` | HTTP 200, certificat vérifié |
| LaBoutik | Nom HTTPS Fedow via `host-gateway` | HTTP 200, certificat vérifié ; son client ne sélectionne pas l'adresse HTTP interne |

Les tâches natives `refill_from_lespass_to_user_wallet_from_ticket_scanned` et `refill_from_lespass_to_user_wallet_from_price_solded` peuvent appeler Fedow depuis Celery. Le problème concerne donc notamment les récompenses de billets/adhésions lorsqu'elles sont activées. Le ping Celery réussi dans l'audit précédent prouvait son lien avec Redis, pas sa capacité à joindre Fedow.

La lecture du catalogue actuel de Smoke compte **0 tarif avec récompense activée, 0 récompense au scan de billet et 0 produit d'adhésion**. Le défaut réseau est confirmé, mais les usages de récompense identifiés ne sont donc pas activés dans cette configuration. Ces compteurs ne constituent pas un inventaire de tous les appels possibles depuis Celery.

Cette preuve ne démontre aucun crédit perdu ou incident financier passé. Les tâches de récompense n'ont pas été exécutées par l'audit et aucun solde n'a été modifié. La recharge Stripe interactive utilise le chemin web, qui répond correctement.

**Correction minimale proposée, non appliquée :** ajouter le réseau `frontend` au worker, comme il l'est déjà au serveur Lespass. Cela ne crée ni volume, ni endpoint public, ni modification du code financier. Il faut ensuite vérifier le même endpoint depuis le worker et un cas de tâche dans un gala de test.

```yaml
lespass_celery:
  networks:
    - frontend
    - lespass_backend
```

Une option plus proche du client amont serait de revenir au transport HTTPS natif avec la résolution locale existante. Le HTTPS a répondu correctement sur Smoke actif. Cela ne prouve pas qu'il fonctionnerait sur un Gala neuf inactif : les scripts actuels utilisent déjà un traitement particulier du certificat pendant l'installation. Ce retour demanderait donc un test du premier démarrage avant retrait de notre transport HTTP.

## 3. Certaines communications ne sont pas locales à chaque Gala

| Appel | Configuration réellement lue | Résolution sur Smoke | Conséquence |
| --- | --- | --- | --- |
| Lespass web/Celery → LaBoutik | `Configuration.server_cashless = https://cashless.galas-am-aix.rezal.fr` | IP publique active `51.44.90.200` | Aucun alias local du nom cashless dans ces conteneurs |
| Fedow → Lespass | Webhook natif d'adhésion vers `https://{Place.lespass_domain}/fwh/membership/{transaction.uuid}` | IP publique active `51.44.90.200` | Aucun alias local du nom Lespass dans Fedow |
| LaBoutik → Lespass/Fedow | Noms publics réaffectés à `host-gateway` | Chemin vers le proxy de sa propre EC2 | Résolution locale prévue pour ces échanges |

Sur **Smoke actif**, l'IP publique revient bien à la même EC2. Sur un **Gala inactif utilisant les mêmes noms publics**, les deux premiers appels viseraient le Gala actif. Cela peut empêcher une synchronisation de produits/adhésions. Le signal Fedow concerne les adhésions faites en caisse ; il est best-effort et journalise l'échec de propagation sans annuler la transaction Fedow. Il ne s'agit pas du webhook Stripe qui crédite la recharge.

Le risque est établi par le code natif, les résolutions DNS et les noms partagés. Aucun webhook financier n'a été déclenché ni replayé pour démonstration. Aucun mélange de bases ni débit vers un autre Gala n'est démontré.

**Correction proposée, non appliquée :** compléter les correspondances locales des pairs dans les Compose de release : nom LaBoutik dans Lespass web/Celery ; nom Lespass dans Fedow. Vérifier aussi les certificats HTTPS sur une EC2 inactive neuve. Ajouter des entrées de résolution ne suffit pas à résoudre un certificat invalide ; ne pas désactiver la vérification TLS du fonctionnement normal.

Une stratégie durable avec des noms internes propres à chaque Gala permettrait davantage de transport natif, mais elle change l'architecture de domaines et dépasse la réparation minimale. Elle n'est pas appliquée par cet audit.

## 4. Les domaines Django secondaires sont bloqués avant Nginx

La règle publique Lespass de Traefik ne contient que `Host(galas-am-aix.rezal.fr)`. Le wildcard `server_name *.galas-am-aix.rezal.fr` de Nginx ne crée pas une route dans Traefik.

Les tests des Host `www`, `festival`, `agenda` au travers de l'entrée HTTPS existante rendent 404, sans le header applicatif `/source/`. Le Host inconnu de contrôle rend aussi 404. Ces tests gardent un SNI et un certificat HTTPS valides pour l'entrée testée ; ils ne prouvent pas la présence d'un DNS/certificat propre à chaque alias.

Cela peut casser des liens natifs historiques sous `festival`, ou empêcher l'accès au portail public/meta conservé en base. Les nouveaux retours Stripe utilisent désormais l'apex correct. Une absence de route pour un alias ne démontre donc pas que le parcours QR actuel sur l'apex est cassé.

**Décision à prendre :** conserver une exposition limitée au Gala, ou rendre accessibles certains domaines natifs. Si des aliases doivent fonctionner, les déclarer explicitement dans Traefik et vérifier DNS/TLS/redirections. Ne pas ouvrir aveuglément tous les sous-domaines avec un wildcard.

## 5. Différences Nginx restantes et portée

Les trois `nginx -t` réussissent. Les fichiers montés sur Smoke correspondent exactement au checkout audité. Aucun port Django/Nginx n'est publié sur l'hôte : seuls 80/443 du proxy d'entrée sont publiés.

| Différence au guide | Effet observé / portée |
| --- | --- |
| Résolveur Docker et upstream variable Lespass | Résolution du service applicatif après recréation ; ce n'est pas un moteur de tenant ni un calcul de paiement |
| Alias administration | Lespass `/adminstaff/` → `/admin/`, LaBoutik `/admin/` → login natif `/adminstaff/login/` ; les requêtes anonymes arrivent toujours à une authentification |
| `/source/` en lecture seule | Publication des sources ; chemin distinct de QR/API/admin, répertoire non listé automatiquement |
| Nginx Fedow ne reprend pas `/media` du guide | Les images Fedow téléversées ne seraient pas servies comme dans le guide. Le dossier média est actuellement vide : aucune image cassée existante n'est démontrée |
| Nginx Fedow n'explicite plus les logs hôte et `X-Real-IP` du guide | Écart d'observabilité à rétablir ou justifier ; pas de modification des calculs de solde |
| Noms Aix écrits dans `server_name` | Configuration moins claire pour un futur autre domaine, même si les règles Traefik et `Host $host` déterminent le routage actuel ; paramétrage à harmoniser |
| Upstreams Fedow/LaBoutik résolus statiquement | Également présents sous forme statique dans le guide ; la reprise après recréation du backend mérite un test, sans attribuer ce risque à l'apex |

Une remise au guide doit reprendre les extraits officiels, puis réintroduire uniquement les règles expressément retenues. Le diff complet est conservé dans `.context/nginx-root-investigation-20261009/nginx-vs-guide.diff`.

## 6. Rectification de la preuve précédente sur le bouton recharge

L'audit précédent décrivait `show_refill_button` comme un champ persistant. **C'est une méthode native.** Le champ de réglage est `force_show_refill_button`, avec `hide_refill_button` prioritaire.

La sonde du témoin manuel avait assigné `show_refill_button=True` sur une instance de modèle, masquant la méthode. Une sérialisation de cette méthode dans le résultat pouvait aussi produire un échec de sonde ; l'ancien échec ne prouve pas un défaut de `Configuration.save()` natif. Cette sonde ne valide pas une activation persistante par le bon champ. Le hash du `BaseBillet/models.py` de l'image manuelle est identique au fichier inspecté ici, ce qui confirme ce contrat.

La recharge TEST effectivement réalisée, son crédit et son rejeu restent des observations valides. La preuve d'activation durable du bouton dans le **témoin manuel** doit être refaite avec le champ natif correct lors d'un prochain témoin. Le code de **notre pipeline** utilise déjà `force_show_refill_button` correctement : sur Smoke, les flags natifs et `configure_gala_refill --check` réussissent. Aucun changement du serveur n'a été effectué pour cette rectification.

## Ordre du travail proposé

1. Conserver l'apex Gala ; corriger la connectivité Celery → Fedow par la configuration réseau minimale.
2. Corriger/tester les échanges entre applications sur un Gala inactif et ses certificats, puis décider des aliases publics utiles.
3. Remettre les règles Fedow de médias/logs du guide si l'objectif reste la fidélité maximale, en préservant les ajouts choisis.
4. Vérifier un premier démarrage neuf, les communications dans les deux sens et un reboot via la pipeline avant alignement final d'Aix. Le témoin natif du bouton recharge devra utiliser le réglage persistant correct.
