"""Free refill amounts retain exact cent values and existing server limits."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(importlib.util.find_spec('rest_framework'), 'requires Django REST framework')
class CawlRefillAmountTests(unittest.TestCase):
    def test_euro_input_cents_compatibility_bounds_and_ambiguous_amounts(self):
        probe = r'''
from django.conf import settings
settings.configure(USE_I18N=False)
from PaiementCawl.validators import RefillAmountInput
for value, cents in [('7.35',735),('7,35',735),('12',1200),('0.50',50),('500.00',50000),(' 12,34 ',1234)]:
    serializer=RefillAmountInput(data={'amount_eur':value})
    assert serializer.is_valid(), (value,serializer.errors)
    assert serializer.validated_data=={'amount':cents}, value
for value in [50,735,50000,'735']:
    serializer=RefillAmountInput(data={'amount':value})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data=={'amount':int(value)}
for value in ['',None,True,'0','-1','0.49','500.01','1.001','NaN','Infinity','1,2.3','not money',[],{}]:
    serializer=RefillAmountInput(data={'amount_eur':value})
    assert not serializer.is_valid(), value
for data in [{},{'amount':735,'amount_eur':'7.35'},{'amount':0},{'amount':49},{'amount':50001},{'amount':7.35}]:
    serializer=RefillAmountInput(data=data)
    assert not serializer.is_valid(), data
print('31 money input cases passed')
'''
        root=Path(__file__).resolve().parents[2]
        result=subprocess.run([sys.executable,'-c',probe],cwd=root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
