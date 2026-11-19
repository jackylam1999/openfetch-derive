import json,urllib.request,urllib.parse,time
U="https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/Parramatta_Council_Data_1/FeatureServer/2/query"
out=[];off=0
while True:
    q={"where":"1=1","outSR":4326,"resultRecordCount":1000,"resultOffset":off,"f":"geojson"}
    d=json.loads(urllib.request.urlopen(urllib.request.Request(U+"?"+urllib.parse.urlencode(q),headers={"User-Agent":"openfetch-derive"}),timeout=120).read())
    g=d.get("features",[]);out+=g;off+=len(g)
    if not g or len(g)<1000 and not d.get("exceededTransferLimit"):break
json.dump({"type":"FeatureCollection","features":out},open("in/official-parramatta.json","w"));print(len(out))
