# Runbook — démarrage, arrêt, dormance

Une EC2 par gala, arrêtée hors saison mais avec son root EBS et son IP publique conservés
(voir `infra/README.md`). Ce runbook couvre le cycle de vie de l'instance et des stacks
Docker dessus — pas le déploiement d'une release (`docs/operations/gala-registry.md` et
`tools/runtime/deploy-release.sh` pour ça).

Prérequis sur l'instance : `/etc/tibillet-gala/<slug>.conf` existe (root, mode 0600 — voir
`tools/runtime/examples/gala.conf.example`), les scripts sont installés sous
`/usr/local/lib/tibillet-gala/` (voir `systemd/tibillet-gala-stacks.service`) et une release
validée a déjà été déployée. Le démarrage échoue volontairement sans
`$(release_dir)/deployed-manifest.json` : il ne doit jamais choisir `latest` ni rebâtir du
code local par défaut.

## Démarrage au boot (automatique)

`systemd/tibillet-gala-stacks.service`, instancié par slug (`tibillet-gala-stacks@<slug>`),
s'exécute au boot :

1. `fetch-runtime-secret.sh` — lit le JSON Secrets Manager et matérialise trois fichiers
   app-spécifiques, `$(runtime_dir)/fedow.env`, `laboutik.env` et `lespass.env` (mode 0600).
   Ils ne peuvent pas être fusionnés : les trois applications utilisent légitimement des
   clés incompatibles (`DOMAIN`, `POSTGRES_DB`, etc.). Nécessite que l'instance profile EC2
   ait accès à ce secret précis (voir `infra/terraform/modules/gala/main.tf`).
2. `start-stacks.sh` — relit le manifeste de release déployé, génère
   `$(runtime_dir)/compose.env` (interpolation Compose non secrète : chemins vers les trois
   fichiers, domaines publics, images immuables), crée le réseau Docker `frontend` s'il
   n'existe pas, puis invoque chaque groupe de `COMPOSE_FILES` avec
   `docker compose --env-file compose.env -f base.yml -f release.yml up -d`. Un reboot ne
   peut donc pas reconstruire Lespass ni tirer `latest`.

```bash
sudo systemctl enable --now tibillet-gala-stacks@gala-am-aix-2027.service
sudo systemctl status tibillet-gala-stacks@gala-am-aix-2027.service
```

## Arrêt propre

```bash
sudo systemctl stop tibillet-gala-stacks@gala-am-aix-2027.service
```

Déclenche `stop-stacks.sh` (`ExecStop`) : il relit le manifeste et le même `compose.env`,
puis exécute `docker compose --env-file compose.env -f base.yml -f release.yml stop` par
stack. Les conteneurs s'arrêtent, les volumes/réseaux et le manifeste restent en place pour
un redémarrage avec exactement la même release.

## Mise en dormance hors saison

1. Backup à jour obligatoire avant l'arrêt (voir `docs/operations/backup-restore.md`) —
   `preflight.sh` refusera un futur déploiement sans backup récent, mais rien n'empêche
   d'arrêter l'instance sans backup : vérifier `$(runtime_dir)/last-successful-backup`
   à la main si le doute existe.
2. `sudo systemctl stop tibillet-gala-stacks@<slug>.service`
3. Arrêter l'instance EC2 (console ou `aws ec2 stop-instances --instance-ids <id>
   --profile gala-elevated`) — le root EBS et l'EIP restent alloués (coût résiduel assumé,
   voir `infra/README.md`).
4. Mettre à jour `registry/<slug>.json` : `"status": "dormant"`.

## Réveil pour un nouveau gala ou un test

1. `aws ec2 start-instances --instance-ids <id> --profile gala-elevated`
2. Attendre `running` puis `aws ec2 wait instance-status-ok ...`.
3. `sudo systemctl start tibillet-gala-stacks@<slug>.service` (si pas déjà `enabled`, le
   boot le fait automatiquement).
4. `tools/runtime/healthcheck.sh /etc/tibillet-gala/<slug>.conf` — confirme que les URLs
   `HEALTHCHECK_URLS` répondent 200/301/302 avant de considérer le gala opérationnel.
5. Mettre à jour `registry/<slug>.json` : `"status"` reflète l'étape réelle
   (`preparation`, `live`).

## Vérification qu'un cycle dormant fonctionne sans changement de données

Avant d'ouvrir un vrai gala, valider une fois sur une preview isolée : stop → EC2 stop →
EC2 start → `tibillet-gala-stacks` start → `healthcheck.sh` passe → même `backup_id` le
plus récent qu'avant l'arrêt (aucune perte, aucune migration inattendue).
