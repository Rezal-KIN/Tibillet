# Tous les montages de la stack active définie dans le dépôt

Lecture des quatre Compose actifs et de leur histoire sur la première lignée du fork. Les fichiers `docker-compose.release.yml` changent les images, pas les volumes. Aucun nouvel inventaire Docker de production.

47 montages distincts par service ; 50 déclarations brutes. Trois lignes LaBoutik sont dupliquées. `rw` est le mode implicite quand `:ro` manque.

| Compose / service | Source hôte → destination conteneur | Type | Mode | Introduction dans le fork |
| --- | --- | --- | --- | --- |
| `deploy/Fedow/docker-compose.yml` / `fedow_postgres` | `./database` → `/var/lib/postgresql/data` | base persistante | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./www` → `/home/fedow/Fedow/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./logs` → `/home/fedow/Fedow/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./settings.py` → `/home/fedow/Fedow/fedowallet_django/settings.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_core/serializers.py` → `/home/fedow/Fedow/fedow_core/serializers.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_dashboard/urls.py` → `/home/fedow/Fedow/fedow_dashboard/urls.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_dashboard/views.py` → `/home/fedow/Fedow/fedow_dashboard/views.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_dashboard/index.html` → `/home/fedow/Fedow/fedow_dashboard/templates/index/index.html` | template remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_dashboard/suivi.html` → `/home/fedow/Fedow/fedow_dashboard/templates/index/suivi.html` | template remplace | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_dashboard/base.html` → `/home/fedow/Fedow/fedow_dashboard/templates/base.html` | template remplace | ro | `01ca8349` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `./custom_patches/fedow_dashboard/public_index.html` → `/home/fedow/Fedow/fedow_dashboard/templates/index.html` | template remplace | ro | `01ca8349` |
| `deploy/Fedow/docker-compose.yml` / `fedow_django` | `../source/admin-templates` → `/home/fedow/Fedow/source_templates` | template remplace | ro | `01ca8349` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./www` → `/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./logs` → `/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `./nginx` → `/etc/nginx/conf.d` | configuration Nginx | rw | `bc5b1a85` |
| `deploy/Fedow/docker-compose.yml` / `fedow_nginx` | `../source/public` → `/source` | offre sources AGPL | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_postgres` | `./database/data` → `/var/lib/postgresql/data` | base persistante | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./backup` → `/Backup` | sauvegardes | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./ssh` → `/home/tibillet/.ssh` | configuration SSH | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./settings.py` → `/DjangoFiles/Cashless/settings.py` | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./install.py` → `/DjangoFiles/administration/management/commands/install.py` | code/configuration Python remplace | ro | `a58a15f8` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./source_templates/login.html` → `/DjangoFiles/webview/templates/login.html` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./source_templates/kiosk_base.html` → `/DjangoFiles/htmxview/templates/kiosk/base.html` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./source_templates/infos.html` → `/DjangoFiles/htmxview/templates/appsettings/infos.html` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `../source/admin-templates` → `/DjangoFiles/source_templates` | template remplace | ro | `01ca8349` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./views.py` → `/DjangoFiles/webview/views.py` (déclaré deux fois) | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./fedow_api.py` → `/DjangoFiles/fedow_connect/fedow_api.py` (déclaré deux fois) | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_django` | `./validators.py` → `/DjangoFiles/webview/validators.py` (déclaré deux fois) | code/configuration Python remplace | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `./nginx` → `/etc/nginx/conf.d` | configuration Nginx | rw | `bc5b1a85` |
| `deploy/Laboutik/docker-compose.yml` / `laboutik_nginx` | `../source/public` → `/source` | offre sources AGPL | ro | `01ca8349` |
| `deploy/Lespass/docker-compose.yml` / `lespass_postgres` | `./database` → `/var/lib/postgresql/data` | base persistante | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./backup` → `/Backup` | sauvegardes | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_django` | `./ssh` → `/home/tibillet/.ssh` | configuration SSH | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_celery` | `./www` → `/DjangoFiles/www` | fichiers www (medias/static/prix) | rw | `e2ad1406` |
| `deploy/Lespass/docker-compose.yml` / `lespass_celery` | `./logs` → `/DjangoFiles/logs` | journaux | rw | `e2ad1406` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `../source/public` → `/source` | offre sources AGPL | ro | `01ca8349` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./www` → `/www` | fichiers www (medias/static/prix) | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./logs` → `/logs` | journaux | rw | `bc5b1a85` |
| `deploy/Lespass/docker-compose.yml` / `lespass_nginx` | `./nginx` → `/etc/nginx/conf.d` | configuration Nginx | rw | `bc5b1a85` |
| `deploy/traefik/docker-compose.yml` / `traefik` | `/var/run/docker.sock` → `/var/run/docker.sock` | socket Docker | ro | `bc5b1a85` |
| `deploy/traefik/docker-compose.yml` / `traefik` | `./acme.json` → `/acme.json` | certificats TLS | rw | `bc5b1a85` |
