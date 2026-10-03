"""Execute source functions with instrumented collaborators; never use real network."""
import ast
import json
import logging
import os
import types
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

root=Path(os.environ.get('AUDIT_SOURCE_ROOT', Path(__file__).resolve().parent))
repo=Path(os.environ.get('AUDIT_REPO_ROOT', root.parent.parent))
class Rejected(Exception):
    def __init__(self, detail=None, code=None): super().__init__(detail)

def load(path, name, scope, classname=None):
    tree=ast.parse(path.read_text())
    parent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname) if classname else tree
    fn=next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name==name)
    fn.decorator_list=[]
    body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),fn]
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(path),'exec'),scope)
    return scope[name]

results=[]
for label,base in [('upstream',root/'laboutik'),('overlay',repo/'deploy/Laboutik')]:
    api=base/'fedow_connect/fedow_api.py' if label=='upstream' else base/'fedow_api.py'
    views=base/'webview/views.py' if label=='upstream' else base/'views.py'
    validators=base/'webview/validators.py' if label=='upstream' else base/'validators.py'
    for method in ('_get','_post','_put'):
        session=Mock(); session.get.return_value=session.post.return_value=session.put.return_value=types.SimpleNamespace(status_code=200)
        scope={'requests':types.SimpleNamespace(Session=lambda:session),'json':json,'logger':logging.getLogger('audit'),
          'settings':types.SimpleNamespace(DEBUG=False),'sign_message':lambda *a:b'test-signature','verify_signature':lambda *a:True,'data_to_b64':lambda d:b'data'}
        fn=load(api,method,scope)
        conf=types.SimpleNamespace(fedow_domain='audit.invalid',fedow_place_admin_apikey='dummy',get_private_key=lambda:None,get_public_key=lambda:None)
        fn(conf,['card'] if method=='_get' else 'card',*([] if method=='_get' else [{}]))
        kwargs=getattr(session,method[1:]).call_args.kwargs
        results.append({'variant':label,'case':method+'_timeout','timeout':kwargs.get('timeout')})
    # Real Commande.validation, till collaborators omitted until missing handler fails.
    scope={'transaction':types.SimpleNamespace(atomic=lambda f:f),'dround':lambda v:Decimal(v),'logger':logging.getLogger('audit')}
    fn=load(views,'validation',scope,'Commande')
    obj=types.SimpleNamespace(carte_db=None,data={'articles':[{'pk':types.SimpleNamespace(methode_choices='BI'), 'qty':1}]})
    tree=ast.parse(views.read_text()); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Commande')
    has_billet=any(isinstance(n,ast.FunctionDef) and n.name=='methode_BI' for n in cls.body)
    class HandlerReached(Exception): pass
    def reached(*args): raise HandlerReached('billet handler reached')
    if has_billet: obj.methode_BI=reached
    try: fn(obj); outcome='completed'
    except Exception as e: outcome=type(e).__name__+': '+str(e)
    tree=ast.parse(views.read_text()); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Commande')
    has_billet=any(isinstance(n,ast.FunctionDef) and n.name=='methode_BI' for n in cls.body)
    results.append({'variant':label,'case':'billet_handler','has_methode_BI':has_billet,
                    'bare_dispatch_observation':outcome,'note':'actual dispatcher; dummy handler marks reachability only, no real ticket created'})
    # Call actual validator on a Fedow network failure: should not interpret it as card-not-found.
    nfc=Mock(); nfc.retrieve.side_effect=ConnectionError('injected Fedow outage')
    cards=Mock(); cards.get_or_create.return_value=(types.SimpleNamespace(uuid_qrcode='existing'),False)
    scope={'FedowAPI':lambda:types.SimpleNamespace(NFCcard=nfc),'CarteCashless':types.SimpleNamespace(objects=cards)}
    fn=load(validators,'validate_tag_id',scope,'DataAchatDepuisClientValidator')
    obj=types.SimpleNamespace(config=types.SimpleNamespace(can_fedow=lambda:True))
    try: fn(obj,'aabbccdd'); err=None
    except Exception as e: err=type(e).__name__
    results.append({'variant':label,'case':'card_lookup_network_failure','create_attempts':nfc.create.call_count,'local_get_or_create_attempts':cards.get_or_create.call_count,'error':err})
    # Subscription API error contract.
    response=types.SimpleNamespace(status_code=400,json=lambda:{'primary_card_fisrtTagId':['invalid']})
    from uuid import UUID, uuid4
    from datetime import datetime
    scope={'_post':lambda *a:response,'logger':logging.getLogger('audit'),'NotAcceptable':Rejected,
           'UUID':UUID,'localtime':lambda:datetime.now(),'Articles':types.SimpleNamespace(ADHESIONS='AD')}
    fn=load(api,'create_sub',scope,'Subscription')
    obj=types.SimpleNamespace(config=types.SimpleNamespace(fedow_place_wallet_uuid='audit-place'))
    try:
        value=fn(obj,wallet=str(uuid4()),amount=100,article=types.SimpleNamespace(methode_choices='AD',fedow_asset=types.SimpleNamespace(pk='asset')),user_card_firstTagId='client',primary_card_fisrtTagId='operator')
        obs={'returned_type':type(value).__name__,'returned':value}
    except Exception as e: obs={'exception':type(e).__name__,'message':str(e)}
    results.append({'variant':label,'case':'subscription_error_contract',**obs})
    # Membership validity check absent from overlay entry points, exact AST names.
    for name,classname in [('check_carte',None),('methode_VT','Commande')]:
        parent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname) if classname else tree
        node=next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name==name)
        calls=[n.func.id for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        results.append({'variant':label,'case':name+'_membership_lookup','calls_fetch_adhesions':'fetch_adhesions' in calls})

report={'scope':'executed source functions with mock HTTP/ORM collaborators; decorators omitted; not full LaBoutik integration','results':results}
(root/'laboutik-results.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
