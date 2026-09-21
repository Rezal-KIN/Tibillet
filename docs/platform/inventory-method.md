# Inventaire lecture seule de TibilletBapts

Cet inventaire établit l'état réel de `TibilletBapts` avant tout import Terraform, création AWS, installation runtime ou livraison applicative.

## Prérequis et scope

- Vérifier d'abord l'identité AWS et le scope :

  ```bash
  aws sts get-caller-identity --profile gala-operator
  python3 tools/validate-runtime-scope.py \
    --account 318629836660 \
    --region eu-north-1 \
    --instance i-0cd4e52913c8ae928 \
    --instance-name TibilletBapts
  ```

- SSH exclusivement via `ssh MACHINE-Guinche-Main`.
- Ne jamais inspecter `Config.Env` d'un conteneur, un `.env`, une clé, un secret Infisical/AWS ou le contenu d'un backup.
- Ne jamais lancer `docker compose up`, `down`, `pull`, `build`, `restart`, `stop`, `start`, une migration ou `tools/start-stacks-on-boot.sh`.
- Les commandes sont limitées à Bapts et doivent rester sans effet de bord.

## Relevé AWS

Collecter en lecture seule pour `i-0cd4e52913c8ae928` :

```bash
aws ec2 describe-instances \
  --region eu-north-1 \
  --instance-ids i-0cd4e52913c8ae928 \
  --profile gala-operator

aws ec2 describe-volumes \
  --region eu-north-1 \
  --filters Name=attachment.instance-id,Values=i-0cd4e52913c8ae928 \
  --profile gala-operator

aws ec2 describe-addresses \
  --region eu-north-1 \
  --filters Name=instance-id,Values=i-0cd4e52913c8ae928 \
  --profile gala-operator

aws ssm describe-instance-information \
  --region eu-north-1 \
  --filters Key=InstanceIds,Values=i-0cd4e52913c8ae928 \
  --profile gala-operator
```

Relever uniquement les métadonnées nécessaires : AMI, type, état, tags, VPC/subnet, security groups, IP/EIP, volumes, chiffrement, instance profile, SSM et snapshots liés.

## Relevé SSH/runtime

Ces commandes sont autorisées car elles n'affichent pas les variables d'environnement des applications :

```bash
ssh MACHINE-Guinche-Main '
  set -eu
  uname -a
  docker --version
  docker compose version
  systemctl list-unit-files --type=service --no-pager | grep -E "tibillet|docker" || true
  systemctl list-timers --all --no-pager | grep -E "tibillet|backup" || true
  crontab -l 2>/dev/null || true
  sudo crontab -l 2>/dev/null || true
  docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
  docker network ls
  git -C /home/ubuntu/TiBillet remote -v
  git -C /home/ubuntu/TiBillet rev-parse HEAD
  git -C /home/ubuntu/TiBillet status --short
  find /home/ubuntu/TiBillet -maxdepth 2 -name "docker-compose*.yml" -print
'
```

Avant toute lecture additionnelle, vérifier que la commande ne révèle ni `.env`, ni secret, ni contenu de sauvegarde. Lorsqu'une configuration Compose est relevée, conserver seulement chemin, nom de stack, état et références d'images/digests non secrets.

## Résultat attendu

Écrire `docs/platform/bapts-runtime-inventory.md` et `docs/platform/bapts-runtime-inventory.json` uniquement après la collecte. Les deux doivent exclure : valeurs d'environnement, tokens, mots de passe, clés, contenus de backup et IP privées non nécessaires.

Classer chaque élément comme `active`, `preserved-stopped`, `excluded`, `local-preview-only` ou `unknown`. L'utilisateur doit approuver ce résultat avant toute mutation de Bapts.
