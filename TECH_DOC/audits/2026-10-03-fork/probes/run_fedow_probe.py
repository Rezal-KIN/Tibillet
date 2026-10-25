"""Compare real Fedow serializers with PostgreSQL and no external requests."""
import importlib.util
import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

root = Path(os.environ.get('AUDIT_SOURCE_ROOT', Path(__file__).resolve().parent))
repo = Path(os.environ.get('AUDIT_REPO_ROOT', root.parent.parent))
sys.path.insert(0, str(root / 'fedow'))
from django.conf import settings
settings.configure(
    SECRET_KEY='isolated-overlay-audit-only', DEBUG=False, TEST=True, STRIPE_TEST=False,
    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'solo', 'rest_framework_api_key', 'fedow_core'],
    AUTH_USER_MODEL='fedow_core.FedowUser', USE_TZ=True, TIME_ZONE='UTC',
    DATABASES={'default': {'ENGINE':'django.db.backends.postgresql', 'NAME':'overlay_audit',
        'USER':'overlay_audit', 'HOST':'127.0.0.1', 'PORT':os.environ['AUDIT_PG_PORT']}},
    CACHES={'default': {'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}},
    DEFAULT_AUTO_FIELD='django.db.models.BigAutoField', MEDIA_ROOT=str(root/'media'),
    REST_FRAMEWORK={'UNAUTHENTICATED_USER':None},
)
real_connect = socket.socket.connect
def isolated_connect(sock, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('External network forbidden in audit: ' + str(address[0]))
    return real_connect(sock, address)
socket.socket.connect = isolated_connect
import django
django.setup()
from django.core.management import call_command
from django.core.cache import cache
from django.db import connection
from fedow_core.models import Asset, Card, CheckoutStripe, Configuration, FedowUser, Origin, Place, Token, Transaction, Wallet
call_command('migrate', verbosity=0, interactive=False)

spec=importlib.util.spec_from_file_location('fedow_overlay_audit', repo / 'deploy/Fedow/custom_patches/fedow_core/serializers.py')
overlay=importlib.util.module_from_spec(spec); spec.loader.exec_module(overlay)
from fedow_core import serializers as upstream


def fixtures():
    call_command('flush', verbosity=0, interactive=False)
    cache.clear()
    primary=Wallet.objects.create(name='Primary')
    Configuration.objects.create(name='Audit', domain='http://audit.invalid', primary_wallet=primary)
    place=Place.objects.create(name='AuditPlace', wallet=Wallet.objects.create(name='Place'))
    other=Place.objects.create(name='OtherPlace', wallet=Wallet.objects.create(name='Other'))
    origin=Origin.objects.create(place=place, generation=1)
    def card(wallet):
        return Card.objects.create(first_tag_id=uuid4().hex[:8], qrcode_uuid=uuid4(), number_printed=uuid4().hex[:8], origin=origin, wallet_ephemere=wallet)
    operator=card(place.wallet); operator.primary_places.add(place)
    client=Wallet.objects.create(name='Client'); customer=card(client)
    local=Asset.objects.create(name='Local', currency_code='LOC', category=Asset.TOKEN_LOCAL_FIAT, wallet_origin=place.wallet)
    fed=Asset.objects.create(name='Federated', currency_code='FED', category=Asset.STRIPE_FED_FIAT, wallet_origin=primary, id_price_stripe='price_audit')
    Token.objects.get_or_create(wallet=client,asset=local)
    Token.objects.get_or_create(wallet=client,asset=fed)
    request=SimpleNamespace(place=place, META={'REMOTE_ADDR':'127.0.0.1'})
    return SimpleNamespace(**locals())


def refill(mod, f, stripe=False, checkout=None):
    data={'sender':str(f.primary.pk if stripe else f.place.wallet.pk), 'receiver':str(f.client.pk),
          'asset':str(f.fed.pk if stripe else f.local.pk), 'amount':1000, 'action':Transaction.REFILL,
          'user_card_firstTagId':f.customer.first_tag_id, 'primary_card_fisrtTagId':f.operator.first_tag_id}
    if checkout: data['checkout_stripe']=str(checkout.pk)
    v=mod.TransactionW2W(data=data,context={'request':f.request})
    valid=v.is_valid()
    return valid, str(v.errors)

results=[]
for label,mod in [('upstream',upstream),('overlay',overlay)]:
    # Healthy local refill.
    f=fixtures(); ok,errors=refill(mod,f)
    results.append({'variant':label,'case':'local_success','accepted':ok,'errors':errors,
        'client_balance':Token.objects.get(wallet=f.client,asset=f.local).value})
    # Real serializer and model, deterministic error before saving REFILL.
    for stripe in (False,True):
        f=fixtures(); asset=f.fed if stripe else f.local
        checkout=CheckoutStripe.objects.create(checkout_session_id_stripe='cs_audit',asset=f.fed,metadata='',status=CheckoutStripe.PAID) if stripe else None
        def fail_refill(instance,*args,**kwargs):
            if instance.action==Transaction.REFILL: raise RuntimeError('injected REFILL failure')
            return original_save(instance,*args,**kwargs)
        original_save=Transaction.save
        error=None
        with patch.object(Transaction,'save',fail_refill):
            try: refill(mod,f,stripe,checkout)
            except Exception as e: error=type(e).__name__ + ': ' + str(e)
        minted=Transaction.objects.filter(asset=asset, action=Transaction.CREATION).count()
        issuer=f.primary if stripe else f.place.wallet
        row={'variant':label,'case':'failed_stripe_refill' if stripe else 'failed_local_refill',
             'error':error,'creation_rows_after_failure':minted,
             'issuer_balance_after_failure':Token.objects.get(wallet=issuer,asset=asset).value,
             'client_balance_after_failure':Token.objects.get(wallet=f.client,asset=asset).value}
        try: row['retry_accepted'],row['retry_error']=refill(mod,f,stripe,checkout)
        except Exception as e: row['retry_exception']=type(e).__name__+': '+str(e)
        row['issuer_balance_after_retry']=Token.objects.get(wallet=issuer,asset=asset).value
        row['client_balance_after_retry']=Token.objects.get(wallet=f.client,asset=asset).value
        results.append(row)
    # Two real PostgreSQL connections pass the same preflight check before either writes.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections
    f=fixtures(); checkout=CheckoutStripe.objects.create(checkout_session_id_stripe='cs_audit_parallel',asset=f.fed,metadata='',status=CheckoutStripe.PAID)
    barrier=Barrier(2,timeout=15)
    original_filter=Transaction.objects.filter
    def synchronized_filter(*args,**kwargs):
        qs=original_filter(*args,**kwargs)
        if kwargs.get('action')==Transaction.CREATION and kwargs.get('checkout_stripe') is not None and 'asset__category' in kwargs:
            exists=qs.exists
            def synchronized_exists():
                answer=exists(); barrier.wait(); return answer
            qs.exists=synchronized_exists
        return qs
    def worker():
        close_old_connections()
        try:
            ok,err=refill(mod,f,True,checkout)
            return {'accepted':ok,'errors':err}
        except Exception as e: return {'exception':type(e).__name__,'error':str(e)}
        finally: connection.close()
    with patch.object(Transaction.objects,'filter',synchronized_filter):
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _:worker(),range(2)))
    results.append({'variant':label,'case':'concurrent_same_stripe_checkout','outcomes':outcomes,
        'creation_rows':Transaction.objects.filter(checkout_stripe=checkout,action=Transaction.CREATION).count(),
        'refill_rows':Transaction.objects.filter(checkout_stripe=checkout,action=Transaction.REFILL).count(),
        'issuer_balance':Token.objects.get(wallet=f.primary,asset=f.fed).value,
        'client_balance':Token.objects.get(wallet=f.client,asset=f.fed).value})
    # Lost-update correction in models remains: deterministic CRE_A CRE_B REF_A REF_B.
    f=fixtures(); b=Wallet.objects.create(name='B'); Token.objects.create(wallet=b,asset=f.local)
    for amount in (1000,2000):
        Transaction.objects.create(ip='127.0.0.1',sender=f.place.wallet,receiver=f.place.wallet,asset=f.local,amount=amount,action=Transaction.CREATION)
    for amount,receiver in ((1000,f.client),(2000,b)):
        Transaction.objects.create(ip='127.0.0.1',sender=f.place.wallet,receiver=receiver,asset=f.local,amount=amount,action=Transaction.REFILL)
    results.append({'variant':label,'case':'model_interleaving','balances':[Token.objects.get(wallet=w,asset=f.local).value for w in (f.place.wallet,f.client,b)]})
    # Field validation of archived asset in fusion (full fusion not invoked).
    f=fixtures(); f.local.archive=True; f.local.save()
    v=mod.TransactionW2W(data={'action':Transaction.FUSION},context={'request':f.request})
    try: v.fields['asset'].run_validation(str(f.local.pk)); accepted=True
    except Exception: accepted=False
    results.append({'variant':label,'case':'archived_fusion_asset_validation','accepted':accepted})
    # VOID shared primary card; no funds to refund, only scope of unlinking.
    f=fixtures(); f.customer.primary_places.add(f.place,f.other)
    v=mod.CardRefundOrVoidValidator(data={'action':Transaction.VOID,'user_card_firstTagId':f.customer.first_tag_id,'primary_card_fisrtTagId':f.operator.first_tag_id},context={'request':f.request})
    ok=v.is_valid()
    results.append({'variant':label,'case':'void_multi_place','accepted':ok,'remaining_places':list(f.customer.primary_places.values_list('name',flat=True))})
    # Malformed historical FED mint with NULL checkout must not poison unrelated local refill.
    f=fixtures(); ch=CheckoutStripe.objects.create(checkout_session_id_stripe='cs_audit_null',asset=f.fed,metadata='')
    creation=Transaction.objects.create(ip='127.0.0.1',sender=f.primary,receiver=f.primary,asset=f.fed,amount=1000,action=Transaction.CREATION,checkout_stripe=ch)
    Transaction.objects.filter(pk=creation.pk).update(checkout_stripe=None)
    ok,errors=refill(mod,f)
    results.append({'variant':label,'case':'local_refill_with_malformed_null_checkout_mint','accepted':ok,'errors':errors})
    # Lespass invoice metadata empty-string normalization, validate_metadata itself.
    f=fixtures(); user=FedowUser.objects.create(username='audit',email='audit@example.invalid',wallet=f.client)
    v=mod.TransactionRefilFromLespassSerializer(context={'request':f.request}); v.asset=f.local; v.receiver=f.client
    failures=[]
    for invoice in ('in_audit_one','in_audit_two'):
        try: v.validate_metadata({'invoice_stripe_id':invoice,'checkout_session_id_stripe':'', **{key:str(uuid4()) for key in ('ligne_article_uuid','membership_uuid','product_uuid','price_uuid')}})
        except Exception as e: failures.append(type(e).__name__)
    results.append({'variant':label,'case':'two_invoices_with_empty_session_id','checkout_rows':CheckoutStripe.objects.count(),'errors':failures})

report={'django':django.get_version(),'postgres':connection.pg_version,
        'scope':'real source serializers and models, migrated isolated PostgreSQL; deterministic injected failures and synchronized two-worker race; no load test or external payment',
        'results':results}
(root/'fedow-results.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
