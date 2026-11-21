import osmium, json, sys
# ways in inner Melbourne bbox with parking orientation tags, plus street-side parking areas
W,S,E,N = 144.93,-37.87,145.02,-37.76
out=[]
class H(osmium.SimpleHandler):
    def way(s,w):
        t={k.k:k.v for k in w.tags}
        ks=[k for k in t if k.startswith('parking')]
        hit = any(('orientation' in k and t[k] in ('diagonal','perpendicular')) or (k.startswith('parking:lane') and t[k] in ('diagonal','perpendicular')) for k in ks) or (t.get('amenity')=='parking' and t.get('parking') in ('street_side','lane'))
        if not hit: return
        try: c=[(n.lon,n.lat) for n in w.nodes]
        except Exception: return
        if not c or not any(W<x<E and S<y<N for x,y in c): return
        out.append({"type":"Feature","properties":{k:t[k] for k in t if k.startswith('parking') or k in('name','highway','amenity')},"geometry":{"type":"LineString","coordinates":c}})
H().apply_file(sys.argv[1], locations=True)
json.dump({"type":"FeatureCollection","features":out},open(sys.argv[2],'w'))
import collections
print(len(out), collections.Counter('area' if f['properties'].get('amenity') else 'street' for f in out))
