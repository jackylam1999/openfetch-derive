Tool calls: 18, minutes: 3

# Site analysis: Lot 23 DP651527, 188 Church Street, Parramatta (NSW)

All coordinates GDA2020 / MGA Zone 56 (EPSG:7856); levels AHD. Not survey data: check against source before design use.

## 1. Lot and address
- Lot: 23//DP651527. Address (NSW Spatial Services address point, 2026-11-08 read): 188 Church Street, Parramatta. LGA City of Parramatta.
- Area: 633 m2 (grid area from the NSW cadastre; plan area 632.298 m2 on the plan label).
- Centre: E 315213.2, N 6256519.5.
- Corners (real boundary vertices): NE 315226.85, 6256532.66; SE 315218.75, 6256501.62; SW 315199.63, 6256506.36; NW 315207.71, 6256537.45.
- Boundary (closed ring): (315221.59, 6256512.49) (315218.75, 6256501.62) (315202.89, 6256505.55) (315199.63, 6256506.36) (315207.71, 6256537.45) (315216.5, 6256535.25) (315226.85, 6256532.66) back to start. Lot is about 27 m x 36 m, long axis roughly north-south, with its street frontage to the north-west/north (kerb to the north, see 5).

## 2. Buildings, heights and where each comes from
There is no official building-outline-with-height dataset for this site. The NSW Spatial Services building footprint layer (2025) is points only here and carries no heights (height_basis "none"). So all heights below are non-official and flagged.

On the lot:
- Murrays' Building (heritage item I464), 3 storeys. OpenStreetMap (volunteer, 2026 read) stated height 8.2 m. Ground about 10 m AHD (council contours), so roof about 18 m AHD. Basis: OpenStreetMap.

Around the site (within about 100 m), heights above ground:
| Building | Distance from lot centre | Height | Basis |
|---|---|---|---|
| 12-storey commercial tower immediately east (footprint 315219-315263 E, 6256491-6256530 N) | 6 m (shares east boundary area) | 38.4 m | OpenStreetMap, estimated from building:levels = 12 at 3.2 m/storey. Not in the LiDAR set (likely newer than the LiDAR survey). |
| Leigh Memorial Church (E of site, ~315296, 6256501) | 85 m | 9.6 m OSM (3 levels est.); 21.3 m LiDAR roof (roof top 31.3 AHD) | OSM estimate vs OpenFetch LiDAR-derived; the two disagree, likely tower or spire in LiDAR |
| PHIVE (~315292, 6256461) | 99 m | 19.2 m | OpenStreetMap, estimate from 6 levels |
| Parramatta Town Hall (~315224, 6256478) | 43 m | 6.4 m OSM; 12.7 m LiDAR | OSM estimate from 2 levels; LiDAR roof |
| St John's Cathedral (~315143, 6256464) | 90 m | 6.4 m OSM; 11.6 m LiDAR | OSM estimate; LiDAR |
| 2-storey shops/commercial to north (~315186-315223, 6256565-6256596) | 49-77 m | 9.8-11.6 m LiDAR; 6.4 m OSM | LiDAR roof (OpenFetch hosted, NSW Spatial Services LiDAR) vs OSM storeys estimate |
| Buildings to west (~315129, 6256520) | 85 m | 8.6 m LiDAR; 6.4 m OSM | as above |

Tallest building within 100 m: the 12-storey building directly east, 38.4 m, OpenStreetMap estimate (basis OpenStreetMap, not official). LiDAR heights are from the LiDAR survey year, so newer buildings are missing; ground comes from council contours, about plus or minus 1 m.

Planning height control for comparison: 42 m (see 3).

## 3. Planning
Source: NSW Planning Portal EPI layers (Parramatta LEP), read 2026-11-08, by point-in-polygon on the lot centre.
- Zone: MU1 Mixed Use.
- Height of Buildings: 42 m (Clause 4.3).
- Floor Space Ratio: 10:1 (Clause 4.4).
- Minimum lot size: no map polygon in the box (layer covers the box and is empty).
- Heritage: the lot is within heritage item I464 "Murrays' Building and potential archaeological site", Local significance (Clause 5.10). Overlay code HO/I464. Grading: Local. Other heritage items nearby but not on the lot include St John's Anglican Cathedral (I465, State), Parramatta Town Hall (I463), Bicentennial Square (I461), Leigh Memorial Uniting Church (I586).
- Other overlays offered by OpenFetch (flood planning areas, acid sulfate soils, bushfire, TOD / low-mid-rise housing areas) were not fetched individually, so I cannot state them for the lot. I did not check them; check these on the Planning Portal.

## 4. Ground levels and fall
No spot heights in the box (NSW Spatial Services spot heights 2012: empty). City of Parramatta 2 m contours (2023) nearby:
- 8 m AHD contour about 65-75 m east/north-east of the lot.
- 10 m AHD contour about 50-60 m east/south-east of the lot, and 10 m further away on the other side.
- 12 m AHD contour about 120 m south, 14 m about 123 m south, 16 m about 125 m south.
So the lot is at about 10 m AHD (OpenFetch assigns 10 m to nearby buildings from the contours, plus or minus 1 m), falling gently to the east/north-east, roughly 1-2 m across the site area, about 2 m over 60 m (about 3%). It rises to the south. This is interpolation from 2 m contours, not a survey.

## 5. Kerbs, footpaths, street trees
- Kerbs: City of Parramatta kerb dataset exists (official council layer, kerb centrelines with asset numbers; undated in the registry). Nearest segments: asset 1010562 (00951_04_L) about 4 m from the north/north-west lot corners; asset 1010563 (00951_04_R) and 1011317/1011318 (01267_01 L/R) 14-30 m to the north. Others 50-95 m away. Indicates the frontage kerb runs just north of the lot boundary.
- Footpaths: OpenFetch has no official footpath layer here (paths only from OpenStreetMap, not fetched). Not available.
- Street trees: the only tree layer (Cumberland City Council 2020) has no features in the box. No official street-tree data for this frontage. Survey on site.

## 6. Transport (straight-line from lot centre)
- Nearest train station: Parramatta Railway Station, 290 m (E 315383.8, N 6256285).
- Light rail (Parramatta Light Rail, tram): Parramatta Square stop 151 m (315363.9, 6256506.1); Church Street stop 274 m (315223.1, 6256793.8); Prince Alfred Square 717 m.
- Bus: Parramatta Bus Interchange 268 m (315330.8, 6256279.2). Individual street bus stops: not available from the official layer here (only interchanges listed).
Source: NSW Spatial Services transport facilities, undated.

## 7. Winter solstice shadow study (21 June, AEST, lat -33.815)
Computed sun positions: 9 am altitude 18.9 deg, azimuth 42.6 deg; 12 noon altitude 32.7, azimuth 359.2; 3 pm altitude 18.1, azimuth 316.3. Method: ray test from 0.5 m grid points on the lot toward the sun against extruded building footprints, existing building on the lot excluded, flat ground assumed at about 10 m AHD.
Using OpenStreetMap heights (includes the 12-storey 38.4 m tower, estimated):
- 9 am: about 37 % of the lot in shadow, all from the 12-storey tower to the east/north-east.
- 12 noon: about 0 % (no building to the north high enough).
- 3 pm: about 0 % (neighbours to the west/north-west are low).
Using LiDAR roof heights (which lack the tower): 0 % at all three times. So the 9 am result depends on the tower height estimate; verify with a survey or the building's DA.

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| NSW Spatial Services, Lots and properties (cadastre) | 2015 (OpenFetch stamp) | CC BY 4.0 |
| NSW Spatial Services, AddressPoint | undated | CC BY 4.0 |
| NSW Spatial Services, Building footprints (points, no heights) | 2025 | CC BY 4.0 |
| NSW Planning, Land Zoning, Height of Building, Floor Space Ratio, Lot Size, Heritage (Parramatta LEP) | 2025 (zone, height); other undated | CC BY 4.0 |
| City of Parramatta, Contours 2 m | 2023 | council licence per OpenFetch terms |
| City of Parramatta, Kerbs | undated | council licence per OpenFetch terms |
| Cumberland City Council, Street trees | 2020 | per OpenFetch terms |
| NSW Spatial Services, Spot heights | 2012 | CC BY 4.0 |
| NSW Spatial Services, Train Station and Bus Station facilities | undated | CC BY 4.0 |
| OpenStreetMap contributors via OpenFetch (building footprints and heights) | read 2026-11-08 | ODbL 1.0 |
| OpenFetch buildings (NSW Spatial Services LiDAR, OSM and Microsoft outlines) | LiDAR year varies | ODbL 1.0 |
Connected via the OpenFetch connector, read 2026-11-08; no daily limit hit. Open web not used.
