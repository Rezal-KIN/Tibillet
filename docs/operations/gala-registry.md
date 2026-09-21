# Registre par gala

Chaque gala a une entrée dans `registry/<slug>.json` (fichier privé, non commité — voir
`.gitignore`). Le schéma est documenté par l'exemple committé :
`registry/examples/gala-am-aix-2027.example.json`.

## Pourquoi un registre séparé de Terraform

Terraform sait déjà dériver l'instance, l'IP publique, l'ARN du secret runtime et le
préfixe S3 de sauvegarde d'un gala (`terraform output galas`, dans
`infra/terraform/outputs.tf`). Dupliquer ces valeurs dans un fichier à jour manuellement
créerait une source de vérité concurrente qui finit par mentir. Le registre ne contient
donc **que** ce que Terraform ne peut pas connaître :

| Champ | Pourquoi ce n'est pas dans Terraform |
| --- | --- |
| `slug` | Clé de jointure vers `terraform output galas` et `var.galas`. |
| `platform` | Choix humain figé pour la durée du gala (v1 ou v2). |
| `deployed_release_id` | Décidé par une promotion manuelle de la pipeline Production, pas par `terraform apply`. |
| `db_size_estimate_mb` | Observé sur l'instance, pas une ressource AWS. |
| `backup_retention_days` | Politique métier/légale, peut différer par gala. |
| `status` | `preparation`, `live`, `frozen`, `dormant`, `archived` — cycle de vie opérationnel. |
| `deployment_locked` | `true` dès l'ouverture du gala ; la pipeline Production le lit pour refuser tout redéploiement hors runbook incident. |

## Utilisation

```bash
# Valeurs dérivées (instance, IP, secret ARN, préfixe backup) :
terraform -chdir=infra/terraform output -json galas

# Valeurs non dérivables (platform, release, rétention, statut) :
cat registry/<slug>.json
```

Ne jamais committer `registry/<slug>.json` : il nomme un domaine et un statut réels. Le
`.gitignore` l'exclut déjà ; seul `registry/examples/*.json` est versionné.
