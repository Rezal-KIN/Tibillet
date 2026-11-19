"""Exercise the domain migration against fictitious ORM rows."""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/runtime/migrate-test-domains.py'
spec = importlib.util.spec_from_file_location('test_domain_migration', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestDomainMigrationTests(unittest.TestCase):
    def test_only_exact_hosts_move(self):
        for original in [module.OLD, module.NEW, 'https://'+module.OLD, 'https://'+module.OLD+'/']:
            result = module.move_host(original, module.OLD, module.NEW)
            self.assertNotIn(module.OLD, result)
            self.assertEqual(module.move_host(result, module.OLD, module.NEW), result)
        for original in ['https://other.example.org', 'https://'+module.OLD+'.evil.test',
                         'http://'+module.OLD, 'https://'+module.OLD+':443',
                         'https://user@'+module.OLD, 'https://'+module.OLD+'/callback',
                         'https://'+module.OLD+'?next=x']:
            with self.subTest(original=original), self.assertRaises(ValueError):
                module.move_host(original, module.OLD, module.NEW)

    def test_all_databases_are_checked_before_any_write(self):
        identity = {'fresh': False, 'place_uuid': 'place', 'wallet_uuid': 'wallet', 'tenant_schema': 'festival'}
        for failure in [1, 2]:
            calls = []
            def shell(service, code):
                calls.append((service, code))
                if len(calls) == failure + 1:
                    raise RuntimeError('unexpected existing pairing')
                return identity if service == 'lespass' else {'changes': 1}
            with patch.object(module, 'shell', side_effect=shell), patch.object(sys, 'argv',
                    ['migrate', '--gala', 'gala-smoke-cawl']), \
                    patch.object(module, 'lespass_code', wraps=module.lespass_code) as lespass, \
                    patch.object(module, 'fedow_code', wraps=module.fedow_code) as fedow, \
                    patch.object(module, 'laboutik_code', wraps=module.laboutik_code) as laboutik:
                with self.assertRaises(RuntimeError):
                    module.main()
                self.assertTrue(all(call.args[-1] is False for builder in [lespass, fedow, laboutik]
                                    for call in builder.call_args_list))
            self.assertEqual(len(calls), failure + 1)

    @unittest.skipUnless(importlib.util.find_spec('django'), 'requires Django for ORM checks')
    def test_idempotence_pairing_balance_preservation_and_wrong_peer_rollback(self):
        probe = r'''
import contextlib,importlib.util,io,json,os,socket,sys,types
from uuid import uuid4
from django.conf import settings
settings.configure(SECRET_KEY='fictitious',INSTALLED_APPS=[],
    DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}})
import django
django.setup()
from django.db import connection,models
spec=importlib.util.spec_from_file_location('migration',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def fixture_model(name,**fields):
    return type(name,(models.Model,),{'__module__':__name__,'Meta':type('Meta',(),{'app_label':'qa'}),**fields})
def text():return models.CharField(max_length=150)
Client=fixture_model('Client',schema_name=text(),categorie=text());Client.SALLE_SPECTACLE='sale'
Domain=fixture_model('Domain',domain=models.CharField(max_length=150,unique=True),
    tenant=models.ForeignKey(Client,on_delete=models.PROTECT),is_primary=models.BooleanField(default=False))
Root=fixture_model('Root',fedow_domain=text(),fedow_ip=text(),key=text())
Lespass=fixture_model('Lespass',server_cashless=text(),key=text(),balance=models.IntegerField())
Paired=fixture_model('Paired',fedow_place_uuid=models.UUIDField(),fedow_place_wallet_uuid=models.UUIDField(),key=text())
Fedow=fixture_model('Fedow',domain=text(),key=text())
Place=fixture_model('Place',uuid=models.UUIDField(primary_key=True),wallet_id=models.UUIDField(),
    lespass_domain=text(),cashless_server_url=text(),cashless_server_ip=text(),key=text())
Cashless=fixture_model('Cashless',billetterie_url=text(),fedow_domain=text(),domaine_cashless=text(),key=text(),balance=models.IntegerField())
Event=fixture_model('Event',full_url=text(),is_external=models.BooleanField(),amount=models.IntegerField())
with connection.schema_editor() as schema:
    for model in [Client,Domain,Root,Lespass,Paired,Fedow,Place,Cashless,Event]:schema.create_model(model)
old,new=m.OLD,m.NEW
public=Client.objects.create(schema_name='public',categorie='root')
gala=Client.objects.create(schema_name='festival',categorie='sale')
meta=Client.objects.create(schema_name='agenda',categorie='meta')
foreign=Client.objects.create(schema_name='unrelated',categorie='sale')
for name,tenant in [('',gala),('www.',public),('festival.',gala),('agenda.',meta),('m.',meta)]:
    Domain.objects.create(domain=name+old,tenant=tenant,is_primary=name in {'','www.','agenda.'})
other=Domain.objects.create(domain='unrelated.example.org',tenant=foreign)
root=Root.objects.create(fedow_domain='fedow.'+old,fedow_ip='192.0.2.1',key='root-key')
lespass=Lespass.objects.create(server_cashless='https://cashless.'+old,key='lespass-key',balance=1234)
paired=Paired.objects.create(fedow_place_uuid=uuid4(),fedow_place_wallet_uuid=uuid4(),key='paired-key')
fedow=Fedow.objects.create(domain='fedow.'+old,key='fedow-key')
place=Place.objects.create(uuid=paired.fedow_place_uuid,wallet_id=paired.fedow_place_wallet_uuid,
    lespass_domain=old,cashless_server_url='https://cashless.'+old,cashless_server_ip='192.0.2.1',key='place-key')
cashless=Cashless.objects.create(billetterie_url='https://'+old+'/',fedow_domain='https://fedow.'+old+'/',
    domaine_cashless='https://cashless.'+old,key='cashless-key',balance=5678)
event=Event.objects.create(full_url='https://festival.'+old+'/event/qa/',is_external=False,amount=500)
external=Event.objects.create(full_url='https://elsewhere.example.org/event/qa/',is_external=True,amount=600)
sys.modules['Customers.models']=types.SimpleNamespace(Client=Client,Domain=Domain)
sys.modules['root_billet.models']=types.SimpleNamespace(RootConfiguration=Root)
sys.modules['BaseBillet.models']=types.SimpleNamespace(Configuration=Lespass,Event=Event)
sys.modules['fedow_connect.models']=types.SimpleNamespace(FedowConfig=Paired)
sys.modules['django_tenants.utils']=types.SimpleNamespace(tenant_context=lambda _:contextlib.nullcontext())
sys.modules['fedow_core.models']=types.SimpleNamespace(Configuration=Fedow,Place=Place)
sys.modules['APIcashless.models']=types.SimpleNamespace(Configuration=Cashless)
socket.gethostbyname=lambda _: '172.17.0.1'
os.environ.update(DOMAIN=new,GALA_LOCAL_FEDOW='1',PAYMENT_PROVIDER='cawl',CAWL_TEST='1',SUB='festival',META='agenda')
def run(code):
    with contextlib.redirect_stdout(io.StringIO()) as output:exec(code,{})
    return json.loads(output.getvalue().splitlines()[-1])
snapshot=list(Domain.objects.values())
identity=run(m.lespass_code(False));assert list(Domain.objects.values())==snapshot
run(m.lespass_code(True));assert run(m.lespass_code(False))['changes']==0
assert not Domain.objects.filter(domain__endswith=old).exists()
assert Domain.objects.get(pk=other.pk).domain=='unrelated.example.org'
assert [(r['tenant_id'],r['is_primary']) for r in Domain.objects.values()]==[(r['tenant_id'],r['is_primary']) for r in snapshot]
os.environ['DOMAIN']='fedow.'+new
run(m.fedow_code(identity,True));assert run(m.fedow_code(identity,False))['changes']==0
os.environ['DOMAIN']='cashless.'+new
run(m.laboutik_code(True));assert run(m.laboutik_code(False))['changes']==0
for row in [root,lespass,paired,fedow,place,cashless]:
    key=row.key;row.refresh_from_db();assert row.key==key
lespass.refresh_from_db();cashless.refresh_from_db();place.refresh_from_db()
assert lespass.balance==1234 and cashless.balance==5678
event.refresh_from_db();external.refresh_from_db()
assert event.full_url=='https://'+new+'/event/qa/' and event.amount==500
assert external.full_url=='https://elsewhere.example.org/event/qa/' and external.amount==600
assert place.wallet_id==paired.fedow_place_wallet_uuid and place.lespass_domain==new
Fedow.objects.filter(pk=1).update(domain='fedow.'+old)
os.environ['DOMAIN']='fedow.'+new
try:run(m.fedow_code({**identity,'wallet_uuid':str(uuid4())},True))
except Place.DoesNotExist:pass
else:raise AssertionError('wrong peer accepted')
fedow.refresh_from_db();assert fedow.domain=='fedow.'+old
os.environ.update(DOMAIN=new,CAWL_TEST='0')
try:run(m.lespass_code(True))
except AssertionError:pass
else:raise AssertionError('production mode accepted')
os.environ['CAWL_TEST']='1'
Domain.objects.filter(domain=new).update(domain='unexpected.example.org')
try:run(m.lespass_code(True))
except AssertionError:pass
else:raise AssertionError('existing database mistaken for a fresh one')
print('ORM migration and preservation checks passed')
'''
        result = subprocess.run([sys.executable, '-c', probe, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

