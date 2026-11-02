# Publication de gala-test sur estia

**Etat au 02/11/2026 : les trois domaines publics repondent 200 en HTTPS,
avec un certificat dedie valide jusqu'au 31/01/2027.** La VM utilise HTTP
prive derriere estia ; les anciens domaines restent des alias en base.
Les fichiers et certificats des autres sites nginx n'ont pas ete modifies.

La pipeline de `tibillet-local-upstream` charge explicitement ce Compose.
Un push sur cette branche declenche le deploiement sur la VM de test.
L'etat Certbot dedie est cree ; le renouvellement et son timer doivent etre
valides puis installes separement sur estia. Aucun reload nginx automatique
n'est configure par les exemples de renouvellement.

La preparation a ete validee contre la base applicative `63ed1ab5`.
Le diagnostic historique Certbot a ete remplace par des comparaisons directes
et des controles fonctionnels : ne pas utiliser `certbot config_changes` pour
un audit suppose en lecture seule (sa version 0.31 peut restaurer des checkpoints).
`nginx -T` lit les fichiers sur disque, pas la configuration en memoire.

## Choix retenu apres clarification

L'application utilise ses vrais domaines. Tailscale reste pour le SSH
administratif, sans tunnel web. Le trafic suit ce chemin :

```text
Visiteur --HTTPS--> estia --HTTP prive--> gala-test:80 --Traefik--> nginx --> Django
                        seules les requetes venant de 192.168.1.10 sont admises
```

| Domaine | Destination |
|---|---|
| gala-test.rezal.fr | tenant public existant |
| cashless.gala-test.rezal.fr | lieu existant, schema lespass (Gala) |
| fedow.gala-test.rezal.fr | service Fedow existant |

La caisse integree reste sur `https://cashless.gala-test.rezal.fr/laboutik/`.
Les autres lieux de demonstration ne sont pas publies. Un nouveau domaine devra
etre ajoute explicitement au DNS, au proxy et au certificat : aucun joker.

## Perimetre protege

- Aucun changement dans `hello.rezal.fr` (Clement), `rezal.fr`, les snippets
  nginx partages, leurs certificats ou leurs liens d'activation.
- Aucun changement DNS, pfSense, AWS ou sur une instance de production.
- Aucun changement des cartes, des soldes ou des identifiants CAWL.
- Aucun redemarrage de nginx. Les rechargements necessaires concernent toute
  sa configuration : comparer les fichiers proteges, tester la configuration
  et verifier les sites temoins. Si un changement concurrent ou inexplique est
  detecte, s'arreter pour l'identifier avec son auteur. Pas de coordination
  systematique avec Clement imposee avant ces controles techniques.
- La VM garde son acces SSH par Tailscale. Le HTTPS local et le tunnel web
  de developpement cessent de servir l'application apres activation.

## Etat initial avant la bascule

Le 02/11/2026 : les trois DNS pointent deja vers taramis ; estia joint la VM
sur le port 80. La VM renvoie 308 meme avec `X-Forwarded-Proto: https` : sa
redirection HTTP vers HTTPS est globale. Ses routes actuelles n'acceptent que
les anciens domaines. Les certificats listes sur estia sont valides, aucun ne
couvre ces trois noms. `ssl_rezal.fr_params` contient lui-meme les chemins du
certificat partage : il ne faut pas l'importer pour notre certificat dedie.

CAWL construit notamment son webhook depuis le domaine principal du lieu
(`PaiementCawl/services.py`). Il faut donc mettre a jour les domaines Django,
pas seulement les regles nginx. Les schemas et contenus restent les memes.

Verification du site de Clement, completee le 02/11/2026 a 13:53 : le certificat
recent de `hello.rezal.fr` est bien presente par estia et la page repond 200.
L'empreinte SHA256 de la page servie et celle obtenue depuis estia directement
sur `172.20.57.129:80` avec le meme Host sont identiques :
`07ffdafcc62a70d4d567446c00a8a139c9d4ac6e8db2b4c697395bbb75aa4ee3`.
Ces elements observables sont actifs. Les dates des fichiers controles sont
stables ; le fichier hello est date d'environ une seconde apres le demarrage
des workers (09:28:09), donc les dates seules ne prouvent pas une equivalence
complete entre disque et memoire. Aucune operation correspondante n'est apparue
dans les extraits de journaux consultes ; cela ne prouve ni erreur ni absence
de rechargement. La verification fonctionnelle leve la necessite d'imposer
une coordination systematique, pas les controles avant chaque rechargement.

## Contenu des fichiers

- `compose.estia.yml` : complement explicite au Compose de la branche cible.
  Il remplace le point d'entree de developpement par HTTP prive sur
  `192.168.1.195:80`, fait confiance aux en-tetes d'estia uniquement et filtre
  l'adresse reseau du proxy. Les trois domaines des conteneurs se resolvent
  vers estia, pour eviter de dependre du retour par l'IP publique du Rezal.
  Mailpit reste un serveur SMTP de test, sans interface publiee par Traefik.
  Compose >= 2.24.4 requis (`!override`/`!reset`), VM observee en 5.6.1.
- `public.env.example` : valeurs publiques a fusionner dans le `.env` existant,
  **jamais un remplacement du fichier de secrets**. Garder tous les identifiants
  CAWL de test et autres secrets ; ne pas restaurer `.env.avant-cawl`.
- `domaines.py` : affiche les changements par defaut. Deux modes explicites
  permettent ensuite une bascule transactionnelle ou son retour arriere. Le
  script refuse les domaines deja attribues ailleurs ou un principal inattendu.
- `nginx-http.conf.example` : premiere phase de validation ACME, reponse 503
  pour le site tant qu'il n'est pas pret.
- `nginx-https.conf.example` : configuration finale des trois noms uniquement.
  En-tetes transmis explicitement ; aucun import des fichiers TLS partages.
- La pipeline et `scripts/lancer_tests.sh` utilisent les domaines publics et
  verifient le certificat HTTPS sans contournement TLS pour ces domaines.
- `inspect-estia.py` : diagnostic en lecture seule. Empreintes des fichiers
  references par nginx, versions, timer Certbot, noms des hooks et reponses
  locales de sites temoins. Aucun dump de configuration ni de cle privee.
- `tibillet-gala-test-certificat.*.example` : service et timer dedies, sans
  rechargement nginx. Non installes. Certbot 0.31.0 et timer global actif
  confirmes par l'utilisateur ; le timer global est preserve.

## Procedure de publication et de retour en service

1. **Photographier l'etat d'estia** : executer `inspect-estia.py` en root et
   conserver sa sortie sur le Mac. Rechercher un changement concurrent ou une
   incoherence avec les controles fonctionnels ; demander son contexte a
   l'auteur seulement si necessaire. `nginx -T` lit le disque : il ne prouve
   pas ce qui est en memoire.
   Confirmer la version Certbot et le renouvellement existant avant emission.
2. **Preparer uniquement nos fichiers sur estia** : fichier
   `/etc/nginx/sites-available/zz-tibillet-gala-test.conf`, lien du meme nom
   dans `sites-enabled`, et repertoire ACME dedie. Le prefixe `zz-` preserve
   l'ordre observe `hello.rezal.fr`, puis `rezal.fr` ; verifier les autres fichiers
   et les directives `default_server` juste avant l'ajout.
   Verifier que tous nos chemins de fichiers, liens, etat Certbot et unites
   systemd sont libres. S'ils existent deja, s'arreter et les identifier avec
   leur auteur ; ne jamais les ecraser automatiquement.
3. **Phase HTTP** : installer notre candidat HTTP, comparer de nouveau les
   empreintes des fichiers existants, verifier `nginx -t`, puis recharger si
   les controles restent coherents. Tester une ressource ACME sur chacun des trois noms
   depuis l'exterieur. Aucun trafic d'application ne part encore vers la VM.
4. **Certificat dedie** : utiliser `certbot certonly --webroot`, avec un etat
   completement separe. Exemple a ajuster a la version observee, **ne pas lancer
   avant les verifications precedentes** :

   ```sh
   sudo certbot certonly --webroot \
     --config-dir /etc/letsencrypt-tibillet-gala-test \
     --work-dir /var/lib/letsencrypt-tibillet-gala-test \
     --logs-dir /var/log/letsencrypt-tibillet-gala-test \
     --no-directory-hooks \
     --pre-hook /bin/true --post-hook /bin/true --deploy-hook /bin/true \
     --cert-name tibillet-gala-test \
     -w /var/lib/letsencrypt/tibillet-gala-test \
     -d gala-test.rezal.fr \
     -d cashless.gala-test.rezal.fr \
     -d fedow.gala-test.rezal.fr
   ```

   Le plugin webroot sert le challenge via notre emplacement ; `certonly`
   n'installe pas de configuration nginx. Verifier aussi les options globales
   Certbot et l'absence de hooks dans notre nouvel etat. Ne pas utiliser
   `certbot --nginx`, `--expand`, `--standalone`, ni l'API DNS OVH.
5. **Preparer et activer notre HTTPS sur estia** : remplacer uniquement notre
   fichier HTTP par le candidat HTTPS, verifier le certificat, comparer les
   empreintes protegees, faire `nginx -t`, puis recharger si les controles
   restent coherents. Les nouveaux domaines ne fonctionneront pas encore tant que la
   VM n'est pas adaptee ; ne pas annoncer leur disponibilite. Cette preparation
   avant la VM permet ensuite a la pipeline de verifier le vrai HTTPS.
6. **Preparer la VM et la pipeline** : sauvegarder sa configuration uniquement
   dans le perimetre approuve ; fusionner les valeurs publiques sans perdre
   les secrets ; integrer le complement Compose et le correctif de pipeline
   dans la vraie branche cible. Tester `git apply --check pipeline.patch` sur
   sa revision courante. Ne pas appliquer le patch a `main` ni utiliser les
   fichiers applicatifs plus anciens du workspace pour deployer la VM.
   Relecture puis lancement explicite : recreation
   des conteneurs de la VM necessaire pour leurs nouveaux reglages.
7. **Domaines Django** : sauvegarder d'abord la sortie du plan hors du checkout,
   dans `~/gala-test-config/`. Le plan se lance sur la VM sans ecriture :

   ```sh
   docker exec -i lespass_django poetry run python manage.py shell \
     < deploy/estia/gala-test/domaines.py
   ```

   La bascule demande explicitement `docker exec -e ESTIA_DOMAIN_MODE=apply`.
   Elle fait de `gala-test.rezal.fr` et `cashless.gala-test.rezal.fr` les principaux
   des tenants public et lespass. Les anciens noms restent de simples lignes
   d'alias en base, sans route HTTP publiee pour eux. Aucune suppression.
   Cette etape doit preceder la verification HTTP et les tests de la pipeline
   (le correctif l'integre apres les migrations).
8. **Verification reelle** : verifier depuis estia le routage des trois noms sur
   `http://192.168.1.195/` avec `X-Forwarded-Proto: https`, puis controle TLS et
   chaines de redirection depuis
   l'exterieur ; connexion utilisateur et CSRF ; QR ; recharge avec une carte
   CAWL de test ; retour navigateur ET reception du webhook signe ; absence
   de double credit. Surveiller aussi les sites temoins existants.
9. **Retirer le contournement web** : fermer uniquement le terminal de l'ancien
   tunnel SSH web sur le Mac. Garder le SSH administratif et Tailscale. Retirer
   la fiche `CONTOURNEMENT-TEMPORAIRE-GALA-TEST.md` de la branche cible lors de
   l'activation publique ; ses instructions de restauration du `.env` ne
   correspondent plus a la configuration publique CAWL. Ne pas supprimer les
   secrets CAWL avec le contournement.

## Renouvellement : point explicite avant ouverture durable

Notre repertoire Certbot est isole. Le timer global ne le renouvellera donc
pas automatiquement. Le timer dedie propose utilise la version 0.31.0 deja
installee. Il reste a verifier le chemin du binaire, les options des fichiers
`cli.ini` globaux et a tester le service avant de l'activer. Les options de
hook de la commande prennent des valeurs explicites ; les repertoires de
hooks sont desactives. Le seul hook de renouvellement journalise un rappel.
Le rechargement pour servir le nouveau certificat doit etre precede des memes
controles des fichiers proteges et de nginx : aucun hook de reload automatique
dans ce lot.
Ne pas considerer la publication exploitable durablement avant d'avoir etabli
la surveillance d'expiration, le renouvellement et le rechargement controle.

## Retour arriere cible

- Sur estia : desactiver uniquement le lien `zz-tibillet-gala-test.conf`, tester
  nginx, comparer les fichiers proteges, puis recharger si les controles restent coherents.
  Ne pas restaurer tout `/etc/nginx` : cela ecraserait du travail concurrent.
- Sur la VM : reexecuter `domaines.py` avec `ESTIA_DOMAIN_MODE=rollback`, retablir
  les valeurs reseau de la configuration precedente et la pipeline precedente,
  puis recreer la pile de test. Les deux anciens principaux sont restaures ;
  les alias ajoutes ne sont pas supprimes. Garder les secrets CAWL de test.
- Les certificats dedies et le repertoire ACME peuvent rester inactifs.
  Aucun effacement de donnees, aucun `down -v`, aucun changement sur les autres
  domaines, aucune copie de cle privee dans Git ou dans le chat.

## Validations et limites

Les controles de publication ci-dessous prouvent le routage et HTTPS. Ils ne
remplacent pas un parcours authentifie ou une recharge CAWL avec retour
navigateur et webhook signe.

Controles effectues le 02/11/2026 :

| Controle | Resultat et limite |
|---|---|
| Fusion Compose avec la base 63ed1ab | Valide ; publication privee 80 seule, TLS de dev retire du routage, filtrage estia, resolution interne des trois noms |
| Routage Traefik 3.7.16 isole sur le Mac | 200 pour les trois noms depuis le client autorise, protocole HTTPS preserve, 403 depuis une autre IP meme avec un en-tete falsifie, ancien nom 404 |
| Methode de ce test | Regles locales equivalentes chargees par fichier ; decouverte Docker ensuite verifiee sur la vraie VM, trois Host en 200 depuis estia et source directe refusee meme avec XFF falsifie |
| nginx 1.14.2 isole sur le Mac | Les deux candidats passent `nginx -t`, avec certificat factice local pour le test TLS |
| Correctif de pipeline | `git apply --check` reussit sur la revision 63ed1ab ; syntaxe du lanceur Bash valide |
| Script de domaines | Plan puis bascule transactionnelle executes sur la vraie VM ; public et lespass uniquement, anciens domaines conserves comme alias |
| Bascule/rollback en base | Six controles passent sur SQLite en memoire avec Django 4.2.30 et le vrai DomainMixin : plan sans SQL d'ecriture, bascule et rollback idempotents, conflit de tenant refuse, principal inattendu refuse, echec du second tenant annulant toute la transaction ; bascule PostgreSQL ensuite executee. Pas de test de concurrence destructif ni de rollback impose a la VM |
| Certbot | Version 0.31.0 ; certificat dedie emis et servi sur les trois noms, expiration 31/01/2027 ; renouvellement dedie encore a tester et installer |
| Services systemd proposes | Structure relue ; verification native systemd et execution a faire sur estia avant activation |
| nginx natif sur estia | Tests et rechargements controles reussis ; fichiers proteges compares avant chaque reload |
| Application et CAWL publics | Trois racines publiques HTTPS 200, redirections HTTP 301, hello inchange ; aucun paiement ni webhook public valide |

Sources techniques : [Traefik EntryPoints](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/),
[Certbot webroot](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot),
[options de Certbot 0.31.0](https://github.com/certbot/certbot/blob/v0.31.0/certbot/cli.py).
