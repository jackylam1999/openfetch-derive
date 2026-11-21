import json,gzip,re,glob,os
from pyproj import Transformer
K='/mnt/project-files/.notes/kerb-top10/'
tr=Transformer.from_crs(4283,7856,always_xy=True)
CORNER=re.compile(r'corner|chord|kink|diagonal|slip|splay|cuts? across|across (a |the )?(side|street|mouth)|cut across|curl|return|hook|turn|stub|jog|bend|fillet|junction|mouth',re.I)
def vd(x):
    v=(x.get('v') or x.get('verdict') or '').upper()
    return v
def load(f):
    d=json.load(open(K+f))
    if isinstance(d,list): return {str(i+1):x for i,x in enumerate(d)}
    return d
L=[]
def add(pack,crop,verd,why,x,y,src):
    L.append(dict(pack=pack,crop=crop,v=vd(verd),why=(verd.get('why') or verd.get('seen') or '')[:160],x=x,y=y,src=src))
# s15
vs=load('s15/lead/r3-verdicts.json'); ks=json.load(open(K+'s15/key-s15-r3.json'))
for c,v in vs.items():
    k=ks[c]; add('s15',c,v,0,k['x'],k['y'],('h',k['line']))
# datum
vs=load('datum/lead/pack-b-verdicts.json'); ks=json.load(open(K+'datum/pack-b-KEY.json'))
for c,v in vs.items():
    k=ks[c]; add('datum',c,v,0,k['at_mga56'][0],k['at_mga56'][1],('n20',k['line_index_nsw-2026-11-20']))
# kn23/24/s11 via dropped src_index
pairs=[('kn23/key-%s.json'%p,'kn23/lead/%s-verdicts.json'%p,'kn23-'+p) for p in 'b1 b2 b3 c3 c4 c5 c6 c7 c8 c9 d1 d2'.split()]
pairs+=[('kn24/pack1-key.json','kn24/lead/pack1-verdicts.json','kn24-1'),('kn24/pack2-key.json','kn24/lead/pack2-verdicts.json','kn24-2')]
pairs+=[('s11-midcut/pack%s-key.json'%p,'s11-midcut/lead/pack%s-verdicts.json'%p,'s11'+p) for p in 'ABCD']
for kf,vf,name in pairs:
    if not os.path.exists(K+vf): print('missing',vf); continue
    ks=json.load(open(K+kf)); vs=load(vf)
    for c,v in vs.items():
        k=ks.get('crop '+c[1:]) or ks.get(c)
        if not k or 'lonlat' not in k: continue
        x,y=tr.transform(*k['lonlat']); add(name,c,v,0,x,y,('drop',k['src_index']))
json.dump(L,open('labels-raw.json','w'))
from collections import Counter
print(len(L),Counter(l['v'] for l in L)); print(Counter(l['pack'] for l in L))
