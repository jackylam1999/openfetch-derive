Tool calls: 25, minutes: 5

# Site analysis: Lot 23 DP651527, Parramatta (NSW)

No street address was given and OpenFetch find_site needs a street number, so I found the lot in the NSW Spatial Services cadastre (SIX Maps) by lot and plan number and gave its centre to OpenFetch. The OpenFetch daily limit was not hit.

## 1. Lot and address
- Lot 23 DP651527 (23//DP651527). Area 632.3 m2 (plan area, cadastre planlotarea; polygon area 633.0 m2).
- Street address: not obtained. The address register could not be searched by lot. Centre is lat -33.81541, lon 151.00346, in Parramatta CBD, City of Parramatta LGA. Check the address against a title search.
- Boundary, GDA2020 MGA zone 56 (EPSG:7856), E,N in m: (315221.1, 6256511.1), (315218.3, 6256500.2), (315202.4, 6256504.1), (315199.2, 6256504.9), (315207.3, 6256536.0), (315216.0, 6256533.8), (315226.4, 6256531.2). Centre about 315212, 6256518.
- Source: NSW Digital Cadastral Database via SIX Maps NSW_Cadastre MapServer, read 2026-11-08, query lotnumber=23 and plannumber=651527 (layer last updated 2016 on the lot record).

## 2. Buildings and heights
OpenFetch official footprints (NSW Spatial Services, 2025) returned only 4 points near the site, no heights (height_basis none). Heights below come from two non-official layers. Treat them with care.
| Building (MGA E,N) | Distance from centre | Height above ground | Basis |
|---|---|---|---|
| On site, 3 storeys (315210, 6256515) | 4 m | 8.2 m | OpenStreetMap, stated height tag |
| Tower, 12 storeys (315236, 6256509) | 26 m | 38.4 m | OpenStreetMap, estimate from storeys x 3.2 m (not surveyed) |
| (315225, 6256479) | 41 m | 12.7 m | OpenFetch LiDAR roof layer, NSW Spatial Services LiDAR |
| (315223, 6256567) | 51 m | 11.6 m | OpenFetch LiDAR |
| 3 storeys (315297, 6256504) | 86 m | 21.3 m | OpenFetch LiDAR (OSM: 9.6 m) |
| 6 storeys (315292, 6256461) | 99 m | 19.2 m | OpenStreetMap, storeys estimate |
Others in the 200 m box are 6 to 11 m. Tallest neighbour within 100 m with a height: 38.4 m (OpenStreetMap, storey estimate). The LiDAR layer has no building at the tower position, so LiDAR is older than it. No official height is available. Levels in AHD: LiDAR ground was 10 to 12 m AHD where found (about +/-1 m).

## 3. Planning (Parramatta LEP 2023, NSW Planning Portal Principal Planning Layers, read 2026-11-08)
- Zone: MU1 Mixed Use at the lot centre. The lot polygon also touches RE1 Public Recreation (I could not measure how much of the lot).
- FSR map: 10:1 (clause 4.4) at the centre.
- Height of Buildings: no map polygon returned for the lot. I did not confirm a height control.
- Heritage: the lot polygon intersects three local heritage items, all "Item - General", significance Local: I463 Parramatta Town Hall and potential archaeological site, I464 Murrays' Building and potential archaeological site, I461 Bicentennial Square and adjoining buildings. At the centre point only I464 returned. Which item applies to the lot itself is not confirmed, so check the heritage inventory. No separate grading beyond "Local" significance.
- Not checked or no data returned: flood, acid sulfate soils (OpenFetch lists these as having data in the box but I did not fetch them), bushfire (empty), minimum lot size (none returned). Overlay list is therefore incomplete.

## 4. Ground levels (AHD)
Source: City of Parramatta 2 m contours (2023, via OpenFetch). No spot heights in the box. Contours near the site: 10 m about 62 m east and 92 m west-north-west, 8 m about 76 m east-south-east, 12 m about 125 m south. Level at the lot is about 9 to 11 m AHD (between the 8 and 12 m contours), falling about 2 m towards the east and south-east over about 80 m. Roughly 1 in 40. A site survey is needed.

## 5. Kerbs, footpaths, street trees
OpenFetch has no kerb data here and no footpath data. No official kerb dataset was found, so I'm saying none exists for this box. Street trees: Cumberland City Council layer returned 0 features in the box (Parramatta is not in that council). Not answered.

## 6. Transport
OpenFetch has no station, tram or bus stop data for this box and the open-web query (Overpass) timed out. Parramatta Station is about 320 m south-east in a straight line (my estimate, from remembered station coordinates, not looked up). Light rail and bus stops: not obtained.

## 7. Shadows, 21 June (AEST), solar angles for -33.815, 151.003
| Time | Sun altitude | Azimuth |
|---|---|---|
| 9 am | 18.8 deg | 43 deg |
| 12 noon | 32.7 deg | 359 deg |
| 3 pm | 18.2 deg | 316 deg |
Ray test over the lot using the extruded footprints above: with OpenStreetMap heights, about 40% of the lot is shaded at 9 am (mainly by the 12-storey tower to the east at 38.4 m; the on-site building also casts shade), and 0% at noon and about 0% at 3 pm. With the LiDAR layer only, no neighbour shades the lot at any time. The 9 am result rests on an estimated height.

## 8. Sources
- NSW Spatial Services Digital Cadastral Database, SIX Maps, 2026 read (record 2016), CC BY 4.0.
- NSW Spatial Services building footprints, 2025, CC BY 4.0 (points only, no heights).
- OpenStreetMap buildings, 2026 read, ODbL.
- OpenFetch buildings (LiDAR roofs), ODbL with NSW Spatial Services LiDAR CC BY 4.0.
- City of Parramatta contours 2 m, 2023, CC BY.
- NSW Planning Portal Principal Planning Layers (Parramatta LEP 2023, zoning amendment 16, FSR amendment 8, heritage), current 2025/2026, CC BY 4.0.
- OpenFetch connector, read 2026-11-08, data_used stamps for footprints, contours, nsw-roofs and osm-buildings-nsw.
