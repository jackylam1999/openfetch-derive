import numpy as np
from ev2 import ALL, B, sides
K=2.17
rows=[]
for b in B:
    for k,G in sides(ALL[b]).items():
        T=[r['d'] for r in G if r['d'] is not None and 0.5<r['d']<9]
        if len(T)<5: continue
        W=np.median([r['w'] for r in G]); s=[r['s'] for r in G if r.get('s') and r['s']<min(8,.35*W)]
        if len(s)<max(5,.4*len(G)): continue
        d=np.clip(K*np.median(s),1,7); e=np.array([abs(x-d) for x in T])
        cwl=W-2*d
        rows.append(dict(b=b,n=len(T),cov=len(s)/len(G),iqr=np.subtract(*np.percentile(s,[75,25])),W=W,cls=G[0]['cls'],d=d,
            ok1=np.mean(e<1),bad3=np.mean(e>3),cw=cwl, c=np.median([r['c'] for r in G])))
import itertools
def rep(name,f):
    R=[r for r in rows if f(r)]; n=sum(r['n'] for r in R); N=sum(r['n'] for r in rows)
    print(f"{name:30s} keep {n/N:.2f} <1m {sum(r['ok1']*r['n'] for r in R)/n:.2f} >3m {sum(r['bad3']*r['n'] for r in R)/n:.3f}")
rep('all',lambda r:True)
for c in (.5,.6,.7,.8): rep(f'cov>={c}',lambda r,c=c:r['cov']>=c)
for q in (.3,.5,.8): rep(f'iqr<={q}',lambda r,q=q:r['iqr']<=q)
rep('cls>=4',lambda r:r['cls'] is not None and r['cls']>=4)
rep('cls<4',lambda r:r['cls'] is not None and r['cls']<4)
rep('d 2-5',lambda r:2<=r['d']<=5)
rep('cov>=.6 iqr<=.5',lambda r:r['cov']>=.6 and r['iqr']<=.5)
rep('cov>=.6 iqr<=.5 d2-5.5',lambda r:r['cov']>=.6 and r['iqr']<=.5 and 2<=r['d']<=5.5)
