#!/usr/bin/env python3
"""Inventaire en lecture seule ; aucun reload, installation ou fichier cree."""
import hashlib
import json
import pathlib
import re
import shutil
import socket
import subprocess
import sys

if socket.gethostname().split('.')[0] != 'estia':
    sys.exit('Ce diagnostic doit etre execute sur estia.')

def run(args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True)
    return result.returncode, result.stdout

nginx = shutil.which('nginx') or '/usr/sbin/nginx'
status, config = run([nginx, '-T'])
if status:
    sys.exit('nginx -T a echoue. Executer nginx -t pour lire les erreurs ; aucun reload.')

# Ne jamais afficher le dump : il peut contenir des en-tetes confidentiels.
paths = re.findall(r'^# configuration file (.+):$', config, flags=re.MULTILINE)
paths += re.findall(r'^\s*ssl_certificate\s+([^;]+);', config, flags=re.MULTILINE)
manifest = {}
for filename in sorted(set(paths)):
    p = pathlib.Path(filename)
    manifest[filename] = {
        'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
        'target': str(p.resolve()),
    }
print(json.dumps({'host': socket.gethostname(), 'files_on_disk': manifest}, indent=2))
print('ATTENTION : nginx -T lit les fichiers sur disque, pas la configuration en memoire.')

for label, args in (
    ('nginx', [nginx, '-v']),
    ('certbot', ['certbot', '--version']),
    ('planification', ['systemctl', 'list-timers', '--all', '--no-pager', 'certbot.timer']),
):
    print('\n' + label)
    if not shutil.which(args[0]) and not pathlib.Path(args[0]).exists():
        print('Outil absent')
        continue
    code, output = run(args)
    print('Binaire :', shutil.which(args[0]) or args[0])
    print(output.strip())

print('\nFichiers de hooks existants (noms uniquement, aucune execution)')
hooks = pathlib.Path('/etc/letsencrypt/renewal-hooks')
if hooks.exists():
    for p in sorted(hooks.rglob('*')):
        if p.is_file():
            print(str(p))

print('\nOptions globales Certbot : noms des options seulement, valeurs masquees')
for p in (pathlib.Path('/etc/letsencrypt/cli.ini'), pathlib.Path.home()/'.config/letsencrypt/cli.ini'):
    if p.is_file():
        keys = re.findall(r'^\s*([a-zA-Z][a-zA-Z0-9_-]*)\s*=', p.read_text(), re.MULTILINE)
        print(str(p), ', '.join(sorted(set(keys))))

print('\nEtat HTTP local des sites partages (en-tetes seulement)')
import http.client
for host in ('hello.rezal.fr', 'gorgu.rezal.fr', 'rezal.fr'):
    conn = http.client.HTTPConnection('127.0.0.1', 80, timeout=5)
    try:
        conn.request('HEAD', '/', headers={'Host': host})
        response = conn.getresponse()
        print(host, response.status, response.getheader('Location', ''))
    except (OSError, http.client.HTTPException) as error:
        print(host, type(error).__name__)
    finally:
        conn.close()
