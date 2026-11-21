import json, glob, sys, numpy as np
from shapely.geometry import shape, LineString, Point
from shapely.strtree import STRtree
from shapely import distance as sdist, points
lots=[];seen=set()
for fn in sorted(glob.glob('in/lots/*.json')):
    for f in json.load(open(fn))['features']:
        o=f['properties'].get('OBJECTID') or f['properties'].get('objectid')
        if o in seen or not f.get('geometry'): continue
        seen.add(o); g=shape(f['geometry'])
        if g.area>5e5: continue
        lots.append(g.boundary)
T=STRtree(lots)
L=json.load(open('h.json'))
STEP=2.0; WIN=60; JUMP=float(sys.argv[1]) if len(sys.argv)>1 else 5; RUN=8
out=[]
for j,c in enumerate(L):
    ln=LineString(c); n=max(2,int(ln.length/STEP))
    P=points([ln.interpolate(i*STEP).coords[0] for i in range(n)])
    idx=T.nearest(P); d=sdist(P,np.array(lots,dtype=object)[idx])
    base=np.array([np.median(d[max(0,i-WIN//2):i+WIN//2]) for i in range(n)])
    # baseline = 25th pct over the window, robust to the bump itself
    base=np.array([np.percentile(d[max(0,i-WIN//2):i+WIN//2],30) for i in range(n)])
    bad=(d-base)>JUMP
    i=0
    while i<n:
        if bad[i]:
            k=i
            while k<n and bad[k]: k+=1
            if (k-i)*STEP>=RUN:
                m=(i+k)//2; x,y=P[m].x,P[m].y
                out.append(dict(line=j,s=i*STEP,e=k*STEP,x=round(x,1),y=round(y,1),dmax=round(float(d[i:k].max()),1),base=round(float(base[m]),1)))
            i=k
        else: i+=1
json.dump(out,open(f'verge-{JUMP}.json','w'))
print(len(out),len({o['line'] for o in out}))
for nm,(x,y) in [('east',(335390,6243297)),('kog',(326496,6238117)),('wat',(334782,6246341))]:
    print(nm,[o for o in out if abs(o['x']-x)<80 and abs(o['y']-y)<80])
