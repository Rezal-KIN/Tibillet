# Contournement temporaire : tester CAWL sur gala-test sans estia

> **Temporaire.** À annuler entièrement (section « Annuler ») dès que estia
> publie `gala-test.rezal.fr`, et **avant** toute mise en production.
> Rien de ce contournement ne doit exister sur une VM de production.

## Pourquoi

Le reverse proxy du Rezal (estia, 192.168.1.10) n'est pas encore configuré pour
gala-test : la VM n'a donc pas d'adresse publique. Pour tester un paiement CAWL
de bout en bout quand même, le navigateur d'un membre de l'équipe atteint la VM
par un tunnel SSH qui passe par Tailscale.

## Principe

```
navigateur ──► https://lespass.tibillet.localhost  (= le Mac lui-même, port 443)
               └─ tunnel ssh ─Tailscale─► gala-test : Traefik 443 ─► Lespass
CAWL (test) ──► renvoie le navigateur sur https://lespass.tibillet.localhost/...
               └─ même tunnel : Lespass vérifie le paiement auprès de CAWL (get_checkout)
```

- **Aucun changement de code, de DNS, de base de données, ni sur estia, pfSense ou OVH.**
- La pile de la VM garde son domaine de test `tibillet.localhost` : la pipeline
  et ses tests en dépendent.
- Le webhook CAWL ne peut pas atteindre la VM (adresse `.localhost`). Ce n'est pas
  gênant : au retour du navigateur, Lespass interroge CAWL et valide le paiement
  (`PaiementCawl/services.py::mettre_a_jour_le_statut`). La vérification de la
  signature du webhook est couverte par `tests/pytest/test_cawl_ventes.py`.

## Ce qui a été mis en place

| # | Où | Quoi |
|---|----|------|
| 1 | VM, `~/gala-test-config/cawl.env` | Identifiants CAWL **de test**, copiés depuis AWS Secrets Manager `tibillet-gala-paris/shared/integrations-stripe-test` (rubrique `cawl`, mode `test`). `chmod 600`. |
| 2 | VM, `~/gala-test-config/.env.avant-cawl` | Copie de sauvegarde du `.env` d'avant le contournement. |
| 3 | VM, `~/gala-test-config/.env` | Bloc ajouté à la fin, entre `# >>> CONTOURNEMENT CAWL` et `# <<< CONTOURNEMENT CAWL` : `PAYMENT_PROVIDER=cawl`, `CAWL_TENANT_SCHEMAS=lespass`, contenu de `cawl.env`. |
| 4 | GitHub Actions | Un passage manuel du workflow `gala-test` (`suite=cawl`) pour redéployer la pile avec ce `.env`. |
| 5 | Mac de la personne qui teste | Le tunnel, lancé à la main seulement pendant le test (voir ci-dessous). Rien d'installé. |

## Utiliser (sur le Mac, à chaque session de test)

1. Arrêter le Traefik local s'il tourne (il occupe le port 443) :
   `docker stop traefik` (ou arrêter Docker Desktop).
2. Ouvrir le tunnel, laisser le terminal ouvert. macOS réserve le port 443 :
   il faut `sudo` (mot de passe de session du Mac). En root, ssh refuse les fichiers
   de configuration de l'utilisateur (« Bad owner or permissions ») : on les ignore
   (`-F /dev/null`) et on donne tout dans la commande (adresse Tailscale de la VM) :
   ```bash
   sudo ssh -N -F /dev/null -i ~/.ssh/gala_test -o IdentitiesOnly=yes -o UserKnownHostsFile=~/.ssh/known_hosts -L 127.0.0.1:443:127.0.0.1:443 -L "[::1]:443:127.0.0.1:443" tibillet@100.123.104.13
   ```
3. Ouvrir `https://lespass.tibillet.localhost/`. Le navigateur prévient que le
   certificat n'est pas reconnu (certificat local de la VM) : accepter pour ce site.
4. Payer avec une carte de test CAWL.
5. Fermer le tunnel : `Ctrl+C` dans le terminal. Relancer le Traefik local si besoin.

## Annuler (revenir à l'état d'avant)

Sur la VM (`ssh gala-test`) :

```bash
cd ~/gala-test-config
cp .env.avant-cawl .env            # retire le bloc CONTOURNEMENT CAWL
rm .env.avant-cawl
# cawl.env : le garder si on passe ensuite à la vraie configuration publique,
# sinon : rm cawl.env
```

Puis relancer le workflow `gala-test` (Actions → « Run workflow », `suite=cawl`),
qui redéploie la pile sans CAWL.

Sur le Mac : rien à faire (le tunnel n'existe que pendant qu'il tourne). Si le
navigateur a mémorisé l'exception de certificat, elle disparaît avec l'historique
du site.

Enfin, **supprimer ce document** du dépôt.

## Vérifier qu'il ne reste aucune trace

```bash
ssh gala-test 'grep -c "CONTOURNEMENT CAWL" ~/gala-test-config/.env; ls ~/gala-test-config'
```

Le compte doit être `0`, et `.env.avant-cawl` ne doit plus exister.
