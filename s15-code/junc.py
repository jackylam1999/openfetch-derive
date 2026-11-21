import json, glob, collections, numpy as np
from shapely.geometry import shape, Point, MultiPoint
from shapely.strtree import STRtree
def junctions():
    seen=set(); deg=collections.Counter()
    for fn in glob.glob('in/roads/*.json'):
        for f in json.load(open(fn))['features']:
            p=f['properties']; o=p.get('objectid')
            if o in seen or not f.get('geometry'): continue
            seen.add(o)
            if p.get('functionhierarchy') in (8,9,10,11) or p.get('roadontype')!=1: continue
            g=shape(f['geometry'])
            for l in getattr(g,'geoms',[g]):
                for c in (l.coords[0],l.coords[-1]): deg[(round(c[0]),round(c[1]))]+=1
    pts=[Point(k) for k,v in deg.items() if v>=3]
    return STRtree(pts),pts
