#!/usr/bin/env python3
"""Set a shared Gala admin login in the three databases, without storing a password.

Run on the Gala host after deployment. Passwords are prompted without echo;
automation may supply a Django PBKDF2 hash on stdin with --password-hash-stdin.
Existing bootstrap accounts retain their email and relationships. Database
backups preserve this configuration across releases.
"""
import argparse
import base64
import getpass
import hashlib
import json
import re
import secrets
import subprocess
from pathlib import Path


SERVICES = ('fedow', 'laboutik', 'lespass')


def django_shell(service, code):
    command = ['docker', 'exec', '-i', '-w',
               '/home/fedow/Fedow' if service == 'fedow' else '/DjangoFiles',
               service + '_django']
    poetry = 'poetry' if service == 'fedow' else '/home/tibillet/.local/bin/poetry'
    command += [poetry, 'run', 'python', 'manage.py', 'shell']
    result = subprocess.run(command, input=code, text=True, capture_output=True)
    if result.returncode:
        # Django tracebacks can echo input or account data. Do not print them.
        raise RuntimeError('Django admin configuration failed for ' + service)
    return json.loads(result.stdout.strip().splitlines()[-1])


def account_code(service, username, password_hash, apply, admin_email):
    return '''import json, os
from django.contrib.auth import get_user_model
from django.db import transaction
from django.contrib.auth.hashers import identify_hasher
from contextlib import nullcontext
service, username, encoded, apply, admin_email = %r
U = get_user_model()
context = nullcontext()
if service == 'lespass':
    from Customers.models import Domain
    from django_tenants.utils import tenant_context
    context = tenant_context(Domain.objects.select_related('tenant').get(domain=os.environ['DOMAIN']).tenant)
with context, transaction.atomic():
    email = os.environ.get('ADMIN_EMAIL', admin_email)
    user = U.objects.select_for_update().filter(username=username).first()
    candidates = U.objects.select_for_update().filter(email=email)
    if service != 'fedow':
        candidates = candidates.filter(is_staff=True)
    bootstrap = candidates.first() if email else None
    if user and (not user.is_staff or (bootstrap and bootstrap.pk != user.pk)):
        raise RuntimeError('Requested username belongs to a different account')
    user = user or bootstrap
    if not user and service != 'fedow':
        raise RuntimeError('Bootstrap admin is missing')
    if apply:
        identify_hasher(encoded)
        user = user or U(username=username, email=email)
        user.username = username
        user.password = encoded
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        if hasattr(user, 'is_superstaff'):
            user.is_superstaff = True
        user.save()
        assert U.objects.get(pk=user.pk).password == encoded
    elif encoded:
        assert user and user.username == username and user.has_usable_password()
        # authenticate() may rehash a valid password with this app's native
        # iteration count. Readiness must tolerate that standard Django update.
        identify_hasher(user.password)
        assert user.is_active and user.is_staff and user.is_superuser
    print(json.dumps({'service': service, 'username': username, 'status': 'configured' if apply else 'ready'}))
''' % ((service, username, password_hash, apply, admin_email),)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gala', required=True)
    parser.add_argument('--username', default='admin')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--password-hash-stdin', action='store_true')
    parser.add_argument('--credentials-file', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,62}', args.gala) or args.gala == 'bapts':
        parser.error('invalid managed Gala slug')
    config = Path('/etc/tibillet-gala/' + args.gala + '.conf').read_text()
    if not re.search(r'^GALA_SLUG=[\"\']?' + re.escape(args.gala) + r'[\"\']?$', config, re.M):
        parser.error('host configuration targets a different Gala')
    encoded = ''
    if args.credentials_file:
        if args.password_hash_stdin:
            parser.error('choose a credentials file or stdin')
        from importlib.util import module_from_spec, spec_from_file_location
        spec = spec_from_file_location('gala_env', Path(__file__).with_name('materialize-runtime-env.py'))
        renderer = module_from_spec(spec)
        spec.loader.exec_module(renderer)
        credentials = renderer.admin_credentials(json.loads(args.credentials_file.read_text()))
        args.username, encoded = credentials['username'], credentials['password_hash']
    if not re.fullmatch(r'[a-zA-Z0-9_.@+-]{1,150}', args.username):
        parser.error('invalid username')
    admin_email = django_shell('laboutik', "import os,json; print(json.dumps(os.environ['ADMIN_EMAIL']))")
    # Check every database before changing any account. A readiness-only run
    # can validate account flags and its usable hash in that same read.
    for service in SERVICES:
        print(json.dumps(django_shell(service, account_code(service, args.username,
            '' if args.apply else encoded, False, admin_email))))
    if not args.apply:
        return
    if encoded:
        pass
    elif args.password_hash_stdin:
        import sys
        encoded = sys.stdin.readline().strip()
        if not re.fullmatch(r'pbkdf2_sha256\$[1-9][0-9]{4,6}\$[a-zA-Z0-9]+\$[a-zA-Z0-9+/]{43}=', encoded):
            parser.error('expected a Django PBKDF2 SHA256 password hash')
    else:
        password = getpass.getpass('Gala admin password: ')
        if not password or password != getpass.getpass('Confirm password: '):
            parser.error('password confirmation did not match')
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 390000)
        encoded = 'pbkdf2_sha256$390000$' + salt + '$' + base64.b64encode(digest).decode()
    for service in SERVICES:
        print(json.dumps(django_shell(service, account_code(service, args.username, encoded, True, admin_email))))


if __name__ == '__main__':
    main()
