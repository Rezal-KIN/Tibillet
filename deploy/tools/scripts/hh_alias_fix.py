import json
p='/DjangoFiles/www/happy_hour_prices.json'
with open(p,'r',encoding='utf-8') as f:
    d=json.load(f)
bars=d.setdefault('bars',{})
source=bars.get("pian's principal",{})
if source:
    bars["pian's"] = dict(source)
    bars["pians"] = dict(source)
    bars["pian s"] = dict(source)
with open(p,'w',encoding='utf-8') as f:
    json.dump(d,f,ensure_ascii=False,indent=2)
print('bars',list(bars.keys()))
print('entries_pians',len(bars.get("pian's",{})))
