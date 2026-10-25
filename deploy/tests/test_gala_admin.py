"""Exercise native Django authentication, which can update a stored hash."""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec('django'), 'requires Django for the ORM regression')
class GalaAdminAuthenticationTests(unittest.TestCase):
    def test_readiness_survives_native_password_rehash_and_rejects_unusable_password(self):
        script = Path(__file__).resolve().parents[1] / 'tools/runtime/configure-gala-admin.py'
        probe = r'''
import importlib.util, contextlib, io, os
from django.conf import settings
settings.configure(SECRET_KEY='isolated-test', INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes'],
    DATABASES={'default': {'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}})
import django
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0)
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
import sys
spec=importlib.util.spec_from_file_location('admin_config', sys.argv[1]); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
os.environ['ADMIN_EMAIL']='admin@example.invalid'
password='isolated-admin-regression'
encoded=PBKDF2PasswordHasher().encode(password,'regressionSalt',iterations=100000)
with contextlib.redirect_stdout(io.StringIO()):
    exec(mod.account_code('fedow','admin',encoded,True,'admin@example.invalid'))
user=authenticate(username='admin',password=password)
assert user is not None
assert user.password != encoded, 'this test must exercise a real native rehash'
with contextlib.redirect_stdout(io.StringIO()):
    exec(mod.account_code('fedow','admin',encoded,False,'admin@example.invalid'))
user.set_unusable_password(); user.save()
try:
    with contextlib.redirect_stdout(io.StringIO()):
        exec(mod.account_code('fedow','admin',encoded,False,'admin@example.invalid'))
except AssertionError:
    pass
else:
    raise AssertionError('an unusable password passed readiness')
'''
        result = subprocess.run([sys.executable, '-c', probe, str(script)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
