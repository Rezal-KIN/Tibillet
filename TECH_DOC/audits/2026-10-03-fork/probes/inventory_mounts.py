"""Read tracked Compose files and find first appearance of each current mount."""
import collections, json, subprocess
from pathlib import Path
import yaml
base='f0f0d82087a7551dae2d3b835bdd6c0dba4c89a9'
root=next(parent for parent in Path(__file__).resolve().parents if (parent/'.git').exists())
configs=[f'deploy/{c}/docker-compose.yml' for c in ('Fedow','Laboutik','Lespass','traefik')]
rows=[]
for path in configs:
    current=yaml.safe_load((root/path).read_text())
    history=subprocess.check_output(['git','log','--first-parent','--reverse','--format=%H',base+'..HEAD','--',path],cwd=root,text=True).splitlines()
    snapshots=[]
    for commit in history:
        raw=subprocess.check_output(['git','show',commit+':'+path],cwd=root,text=True)
        snapshots.append((commit,yaml.safe_load(raw)))
    def classify(src):
        if src.endswith('.py'): return 'code/configuration Python remplace'
        if 'source_templates' in src or 'admin-templates' in src or src.endswith('.html'): return 'template remplace'
        if 'database' in src: return 'base persistante'
        if src.endswith('/www'): return 'fichiers www (medias/static/prix)'
        if src.endswith('/logs'): return 'journaux'
        if src.endswith('/backup'): return 'sauvegardes'
        if src.endswith('/ssh'): return 'configuration SSH'
        if src.endswith('/nginx'): return 'configuration Nginx'
        if src.endswith('/public'): return 'offre sources AGPL'
        if src.endswith('/acme.json'): return 'certificats TLS'
        if src.endswith('docker.sock'): return 'socket Docker'
        return 'autre'
    for service,config in current['services'].items():
        for raw,count in collections.Counter(config.get('volumes',[])).items():
            source,target,*mode=raw.split(':')
            intro=next(commit for commit,snap in snapshots if raw in snap.get('services',{}).get(service,{}).get('volumes',[]))
            rows.append({'compose':path,'service':service,'source':source,'target':target,'mode':mode[0] if mode else 'rw',
                         'category':classify(source),'declarations':count,'introduction_first_parent':intro})
report={'scope':'tracked active stack definitions; no new live Docker inspection',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        'rows':rows,'unique_mounts_per_service_total':len(rows),'raw_declarations_total':sum(r['declarations'] for r in rows)}
out=root/'TECH_DOC/audits/2026-10-03-fork'
(out/'volumes.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
lines=['# Tous les montages de la stack active définie dans le dépôt','',
       'Lecture des quatre Compose actifs et de leur histoire sur la première lignée du fork. Les fichiers `docker-compose.release.yml` changent les images, pas les volumes. Aucun nouvel inventaire Docker de production.', '',
       f"{len(rows)} montages distincts par service ; {report['raw_declarations_total']} déclarations brutes. Trois lignes LaBoutik sont dupliquées. `rw` est le mode implicite quand `:ro` manque.",'',
       '| Compose / service | Source hôte → destination conteneur | Type | Mode | Introduction dans le fork |',
       '| --- | --- | --- | --- | --- |']
for r in rows:
 lines.append(f"| `{r['compose']}` / `{r['service']}` | `{r['source']}` → `{r['target']}`"+(' (déclaré deux fois)' if r['declarations']>1 else '')+f" | {r['category']} | {r['mode']} | `{r['introduction_first_parent'][:8]}` |")
(out/'VOLUMES.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'unique_mounts':len(rows),'declarations':report['raw_declarations_total'],'introduction_commits':sorted(set(r['introduction_first_parent'][:8] for r in rows))}))
