# Infisical — Gestion des secrets

Infisical est utilisé pour stocker et récupérer les secrets (`.env`) de manière sécurisée, sans les mettre dans git.

Le projet est hébergé sur [Infisical Cloud](https://app.infisical.com) sous l'organisation Rezal.

---

## Première configuration sur un nouveau serveur

### 1. Installer le CLI Infisical

```bash
curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | sudo bash
sudo apt install infisical -y
```

### 2. Récupérer les credentials de la Machine Identity

Dans l'interface Infisical :
- **Organization** → **Access Control** → **Machine Identities**
- Sélectionne l'identité `rezal-server`
- Copie le `Client ID` et génère un nouveau `Client Secret`

### 3. Configurer les credentials sur le serveur

```bash
bash tools/setup_infisical.sh
```

Le script te demande le `Client ID` et le `Client Secret`, les stocke dans `~/.infisical-credentials` (chmod 600) et les charge automatiquement à chaque session.

---

## Modifier les credentials existants

Pour mettre à jour les credentials (ex : après rotation du secret) :

```bash
bash tools/setup_infisical.sh
```

Le script affiche les valeurs actuelles masquées et permet de ne modifier que ce qui a changé.

---

## Récupérer un .env depuis Infisical

Une fois les credentials configurés :

```bash
# Fedow
infisical export --projectId=54d21571-81e2-48ae-8853-188230ce3394 --env=prod > Fedow/.env

# Lespass
infisical export --projectId=54d21571-81e2-48ae-8853-188230ce3394 --env=prod > Lespass/.env

# Laboutik (secrets communs — compléter ensuite DOMAIN, GALA_ID, ROUTER_NAME, MAIN_ASSET_NAME)
infisical export --projectId=54d21571-81e2-48ae-8853-188230ce3394 --env=prod > Laboutik/.env

---

## Variables à renseigner manuellement par instance Laboutik

Ces variables sont spécifiques à chaque événement et ne sont pas dans Infisical :

| Variable | Description | Exemple |
|---|---|---|
| `DOMAIN` | Domaine de la caisse | `mon-bal.cashless.galas-am-aix.rezal.fr` |
| `GALA_ID` | Identifiant unique de l'événement | `MON_BAL_2026` |
| `ROUTER_NAME` | Nom du router Traefik (unique) | `laboutik_mon-bal` |
| `MAIN_ASSET_NAME` | Nom de la monnaie | `Mon Bal Coin` |

---

## Sécurité

- `~/.infisical-credentials` est en `chmod 600` — jamais versionné dans git
- Les `Client Secret` peuvent être révoqués depuis l'interface Infisical à tout moment
- En cas de compromission d'un serveur : révoquer son identité dans Infisical suffit à couper l'accès
