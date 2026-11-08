Tool calls: 28, minutes: 12

# Site analysis: Lot 23 DP651527, 188 Church Street, Parramatta NSW 2150

All coordinates are GDA2020 MGA Zone 56 (EPSG:7856); levels are AHD. Everything is fetched live on 8 Nov 2026 from public NSW government ArcGIS services unless marked OSM or estimate. Where I could not find an official source I say so rather than guess.

## 1. The lot
- Lot / plan: Lot 23 DP651527 (lotidstring `23//DP651527`)
- Address: 188 Church Street, Parramatta (NSW Geocoded Addressing Theme, address point inside the lot)
- Area: 632.3 m2 (plan area 632.298 m2, NSW Cadastre `planlotarea`, lot last updated 2016-02-25)
- Boundary (7 vertices, E, N): 
  - NW 315207.25, 6256536.04
  - NE 315226.39, 6256531.24
  - 315221.13, 6256511.07 (E side step)
  - SE 315218.29, 6256500.20
  - SW 315199.17, 6256504.94 (with 315202.44, 6256504.13 on the south side)
  - Approximate centre 315211, 6256518 (eyeballed from the vertices, not a surveyed centroid)
- Edge lengths from the vertices: roughly 32 m west side, 20 to 25 m north side, 20 m south side. The frontage street is not stated in the data; the address register says Church Street. Check against the plan.

## 2. Buildings on and around the site
No official building-footprint or height dataset was found. All footprints/heights below are OpenStreetMap (OSM, queried 8 Nov 2026, database timestamp 2026-06-01). Most OSM buildings here carry only `building:levels`, so I converted levels at 3.5 m per level and label those as ESTIMATES.

| Building | Dist. from centre | Height | Basis |
|---|---|---|---|
| Murrays' Building (on site, OSM way 562090522) | 2 m | about 10.5 m (3 levels) | estimate, levels x 3.5 |
| Parramatta Town Hall | 43 m | about 7 m (2 levels) | estimate |
| Buildings north, Church St (ways 562111495/6/4/3) | 50 to 71 m | about 7 m each (2 levels) | estimate |
| PHIVE | 95 m | about 21 m (6 levels) | estimate |
| Leigh Memorial Church | 91 m | about 10.5 m (3 levels) | estimate |
| 562090528 (west, Church St) | 151 m | about 24.5 m (7 levels) | estimate |
| 4 Parramatta Square | 187 m | 154 m (OSM `height` tag, 34 levels) | OpenStreetMap |
| Western Sydney Univ. Parramatta City Campus | 211 m | 65 m (OSM `height` tag, 16 levels) | OpenStreetMap |
| 6&8 Parramatta Square | 115 m | no height tag | none given |

Tallest neighbour within 100 m with a height: PHIVE, about 21 m, estimate from levels. The tall towers (4 Parramatta Square 154 m, WSU 65 m) are beyond 100 m, to the south-east. Heights are above ground, not AHD tops. The LEP height-of-buildings map for the lot is "Complex Area" (no numeric metre limit, see section 3).

## 3. Planning (Parramatta LEP 2023; NSW Planning Portal spatial services, queried at the lot centre)
- Zone: MU1 Mixed Use (Land Zoning Map, Amendment No 16, currency 2026)
- Height of Buildings: "CA" Complex Area, i.e. no single numeric height; controlled by Clause 4.3 and Parramatta CBD provisions (sun access, Cl 7.x)
- Floor Space Ratio: 10:1 (Map Amendment No 8)
- Heritage: item I464 "Murrays' Building and potential archaeological site", Item - General, significance Local, Clause 5.10. The lot itself is the listed item. I did not query heritage conservation areas or nearby items.
- Acid Sulfate Soils: Class 4
- Sun Access Protection: Parramatta Square (label 4). This directly constrains massing.
- Additional Local Provisions, Parramatta City Centre: Clause 7.26 (and City Centre Area 1)
- Key Site: B
- Floodplain Risk Management area (Church Street North Precinct amendment)
- Land Use and Transport Integration: Category A
- Clause 7.27 map (IUD layer) applies
- State level layers present at the point (land application only, not individually interpreted): SEPP Biodiversity and Conservation (Sydney Harbour Catchment), SEPP Housing 2021, Transport and Infrastructure 2021 land application, Sustainable Buildings (BASIX climate zone 56, postcode 2150)
- Not checked: bushfire, airport (OLS), flood extents/levels, DCP controls. Obtain a s10.7 certificate and Council flood information.

## 4. Ground levels (AHD) and fall
Only the NSW topographic contour layer (2 m interval) and one spot height were available. No LiDAR DEM could be read (the NSW elevation image service needs a token; ELVIS download not done).
- The lot lies between the 10 m contour (about 80 to 95 m to the north/east/west) and the 12 m contour (about 115 to 150 m to the south).
- Interpolated: roughly 10 to 11 m AHD across the site (about 10.5 m centre), rising slightly to the south, falling gently to the north, about 1% (under 1 m over the lot depth).
- Confidence is low: contours are old (the source record dates to 2001 to 2012) with a stated vertical accuracy of up to 5 m. Commission a detail survey or use 1 m LiDAR from ELVIS for design levels.

## 5. Kerbs, footpaths, street trees
- Kerbs and footpaths: I found NO official kerb or footpath dataset for the City of Parramatta (the Council open-data hub lists 56 datasets, mostly parks/assets; none for kerbs, footpaths or street trees). So no official kerb data is available; a detail survey is needed.
- Trees: OSM has about 28 tagged trees within 80 m (nearest 17 m, 18 m, 21 m, 21 m, 26 m from the centre). No species or heights. This is OSM only, not a council street-tree inventory.
- OSM has no kerb lines tagged in the area.

## 6. Transport (straight-line distances from the lot centre, MGA)
- Nearest train station: Parramatta Railway Station, about 291 m (NSW FOI Transport Facilities, 315383, 6256284). Harris Park is about 960 m.
- Light rail: Parramatta Square Light Rail Stop about 153 m (315363, 6256505); Church Street stop about 274 m (315223, 6256792).
- Bus: Parramatta Bus Interchange about 268 m (NSW FOI, 315330, 6256278); OSM Parramatta Station Stand B1 about 212 m, Stand A1 217 m, "George & Church Street" 201 m, "Westfield Parramatta, Argyle St" 172 m.

## 7. Winter solstice shadow study (21 June, AEST, Parramatta)
Method: solar position by standard NOAA-style equations at lat -33.8154, lon 151.0035; neighbours modelled as 25 m x 25 m boxes at their OSM centre points with the heights in section 2 (buildings with no tag assumed 8 m). The site's own building is excluded. This is a rough screening, not a certified shadow diagram: footprints are approximate and heights are mostly level-based estimates.

| Time | Sun altitude | Azimuth | Result on the lot |
|---|---|---|---|
| 9 am | 18.9 deg | 42.6 deg (NE) | about 13% of the lot shaded, from a low neighbouring building to the NE (shadow about 2.9 m long per metre of height... 29 m per 10 m) |
| 12 noon | 32.7 deg | 359 deg (N) | 0% from neighbours (15.6 m shadow per 10 m of height pointing south; nearest northern buildings are only about 7 m high and 50 m away) |
| 3 pm | 18.1 deg | 316 deg (NW) | 0% from neighbours (shadows point south-east; nearby north-west buildings too low or far) |

Caveats: the tall towers (4 Parramatta Square, WSU) lie south-east, so they do not shade the lot at these times (they would at early morning only). The Sun Access Protection plane (Parramatta Square) is in force over the lot and limits what you can build, which matters more for the design than existing shadow. Model proper footprints and survey heights before relying on this.

## 8. Sources
| Source | Used for | Year / currency | Licence |
|---|---|---|---|
| NSW Spatial Services, NSW Cadastre (maps.six.nsw.gov.au NSW_Cadastre MapServer, layer 9, `23//DP651527`) | lot, area, boundary | live 8 Nov 2026; lot updated 2016 | CC BY 4.0 (NSW Spatial Services) |
| NSW Spatial Services, Geocoded Addressing Theme | address | live 8 Nov 2026 | CC BY 4.0 |
| NSW Dept Planning, Housing and Infrastructure, EPI Primary / Principal Planning Layers, Development Control, Protection (mapprod3.environment.nsw.gov.au) | zone, FSR, height, heritage, ASS, other LEP layers | Parramatta LEP 2023, currency 2025 to 2026 | CC BY 4.0 |
| NSW Spatial Services, Elevation and Depth Theme (contours, spot heights) | ground levels | records 2001 to 2012 | CC BY 4.0 |
| NSW Spatial Services, FOI Transport Facilities and Transport Theme | train, light rail, bus interchange | live 8 Nov 2026 | CC BY 4.0 |
| OpenStreetMap via Overpass (private.coffee mirror) | building footprints/levels/heights, trees, bus stops | OSM data 2026-06-01 | ODbL 1.0 |
| City of Parramatta open data hub (open-data-parracity.hub.arcgis.com) | checked for kerbs/footpaths/trees: none found | 2026 | n/a |
| Own calculation (python) | sun position, shadows, interpolated levels | 2026 | n/a |

Licences are what these agencies normally publish (NSW Government open data is CC BY 4.0); I did not open each licence page.
