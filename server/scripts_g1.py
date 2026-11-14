import sqlite3, json, sys, collections
from threshold.config import CACHE
from threshold.facts.load import cached_plan
c=sqlite3.connect(CACHE/'measures/measures.sqlite')
sids=[r[0] for r in c.execute('select sid from measures where garages>0 order by sid limit 40')]
stat=collections.Counter()
for sid in sids:
    p=cached_plan(sid)
    if p is None: stat['noplan']+=1; continue
    for r in p['rooms']:
        if r.get('label')!='Garage': continue
        ops=[o for o in p['openings'] if r['id'] in (o.get('rooms') or [])]
        ext=[(o['type'],round(o['width'] or 0,2),round(o.get('height') or 0,2),len(o['rooms'])) for o in ops]
        print(sid[:4], r['id'][:5], 'area',round(r.get('area') or 0,1),'w',r.get('width') and round(r['width'],2),'d',r.get('depth') and round(r['depth'],2),'h',r.get('height') and round(r['height'],2),'poly',len(r.get('polygon') or []), ext)
