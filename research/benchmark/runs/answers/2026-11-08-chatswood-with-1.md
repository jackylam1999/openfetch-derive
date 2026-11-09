Tool calls: 17, minutes: 4

# Site analysis: Lot 1 DP724850, Chatswood NSW (Willoughby LGA)

All coordinates GDA2020 / MGA Zone 56 (EPSG:7856). Levels in AHD. Not survey data; check against source before design use. OpenFetch connector was used as main source; no daily limit was hit. Contours were fetched straight from NSW Spatial Services' public map service.

## 1. Lot and address
- Lot: **1//DP724850** (Lot 1, DP 724850). Official NSW Spatial Services lot layer (2015 vintage, queried live 2026-11-08).
- Area: **1,617 m2** (MGA grid area from plan, 1617.006; not the title area).
- Address: the register returned no street address when searched by lot id (address = null). I did not get an address-register match, so confirm the street address with the client or the title.
- Boundary corners (real lot vertices, MGA 56):

| Corner | Easting | Northing |
|---|---|---|
| NE | 331565.73 | 6258852.19 |
| SE | 331584.53 | 6258779.67 |
| SW | 331566.84 | 6258772.72 |
| NW | 331542.38 | 6258842.97 |
| Centre (extent middle) | 331563.46 | 6258812.45 |

Full boundary (16 vertices, clockwise from NW): (331542.38,6258842.97) (331546.08,6258844.43) (331565.73,6258852.19) (331572.95,6258819.26) (331573.28,6258818.27) (331583.97,6258786.15) (331584.53,6258779.67) (331579.21,6258777.58) (331566.84,6258772.72) (331556.66,6258805.43) (331554.2,6258804.46) (331550.28,6258817.52) (331551.42,6258817.95) (331550.57,6258820.13) (331550.53,6258820.11) (331545.56,6258832.95). The lot is long and narrow (about 42 x 80 m extent), long axis roughly NNE-SSW, with a notch on the west side.

## 2. Buildings on and around the site, with heights
Official building footprints (NSW Spatial Services, 2025) return only one point near the lot (331538,6258801) with **no height**. So all heights below are NOT official. They come from OpenStreetMap (OSM, ODbL, community mapped, "NOT OFFICIAL") via OpenFetch. "stated" = OSM height tag; "storeys" = building:levels x 3.2 m; "lidar" = OpenFetch-made layer from NSW LiDAR 2020 (roof top above ground, ODbL/CC BY 4.0). Positions can be several metres off.

On the lot (OSM): 8-storey building, 25.6 m (storeys, ~331550-331581, 6258771-6258820); 4-storey, 12.8 m (storeys; ~331542-331568, 6258814-6258849).

Around the site (centroid distance from lot centre):

| Building (approx location E,N) | Height m | Basis | Dist m |
|---|---|---|---|
| NW tower (331505,6258876) | 87 (18 levels) | OSM stated | 82 |
| N tower (331574,6258898) | 71 (13 levels) | OSM stated | 87 |
| Building to SSW (331545,6258720) | 35 | OSM stated | 94 |
| E building (331640,6258840) | 27 | OSM stated | 84 |
| E/over-rail building (331600,6258830) | 26 (min height 9 m, elevated) | OSM stated | 39 |
| S building (331570,6258735) | 16 (LiDAR 18.2) | OSM stated / lidar 2020 | 76 |
| W building (331510,6258790) | 14 | OSM stated | 71 |
| N low block (331573,6258879) | 12.8 (LiDAR 10.5) | storeys / lidar 2020 | 69 |
| NW low block (331528,6258869) | 11 | OSM stated | 66 |
| W 3-storey (331525,6258805) | 9.6 (LiDAR 14.4) | storeys / lidar 2020 | 34 |
| Farther: 76 m (331465,6258860, 115 m away), 85 m (331685,6258740, 140 m), 45 m (331560,6258690, 123 m) | | OSM stated | >100 |

**Tallest neighbour within 100 m: 87 m, basis OpenStreetMap (not official).** LiDAR heights differ from storey estimates by several metres, so treat all as +/- 3 m or worse. No ground level for buildings could be computed (no spot heights; see section 4), so building tops in AHD are not given; add ground approx 100-104 m AHD (section 4).

## 3. Planning zone, overlays, heritage (Willoughby LEP 2012, Amendment 34, NSW Planning, 2025 data, CC BY 4.0)
- Zone: **E2 Commercial Centre** (covers the lot and surrounds). Nearby: MU1 Mixed Use south of the rail corridor, SP2 Railway (rail corridor), RE1 Public Recreation (Garden of Remembrance, east-south-east).
- Height of Buildings: **max 246.8 m RL (AHD)** over the lot (">100" class, polygon units "m(RL)"). That is roughly 145 m above existing ground (~102 m AHD). The lot's southern tip touches the edge of the adjoining 90 m (above ground) height area. Nearby low areas: 7 m.
- Floor Space Ratio: no FSR polygon returned over the lot. Nearest is 6:1 about 20 m south of the lot's southern end (and 2.5:1 far NE). Check the LEP FSR map / clause 4.4 for the lot directly.
- Minimum lot size: none returned in the box.
- Heritage: **no heritage item or conservation area on the lot.** Nearby (not on the lot): I236 Garden of Remembrance (local, landscape item, ~65 m east-south-east), I239 Orchard Tavern incl. interiors (local, ~110 m north-east), C11 South Chatswood Conservation Area (corner of the box, ~130 m south-east). No State Heritage Register grading was available in the data; I give no grading.
- Other layers exist for this box (flood planning, acid sulfate soils, bushfire, TOD/Housing SEPP, town centres) but I did not fetch them. Check those before relying on this list as "every overlay".

## 4. Ground levels (AHD) and fall
No official spot heights in the box (NSW Spatial Services spot height layer returned nothing), and the connector had no contours. I queried the NSW Spatial Services Elevation and Depth theme **Contour** layer directly (2 m interval, captured 2009 vintage per record; CC BY 4.0). Nearest contour to each point:
- SE and SW corners: **100 m AHD** (contour at 0-2 m / ~19 m)
- Centre: **102 m AHD** (5 m away)
- NE corner: **102 m AHD** (18 m)
- NW corner: **104 m AHD** (19 m)
Fall: about **4 m**, from about 104 m (north-west) to about 100 m (south), roughly 5 percent falling to the south/south-east over about 80 m. Values are +/- 1 m (contour reading). Commission a survey for design levels.

## 5. Kerbs, footpaths, street trees along the frontage
- Kerbs: **no official council or state kerb dataset exists here** in the connector; the only source is OpenStreetMap kerb lines, which returned 0 features in the box. Draw kerbs from survey.
- Footpaths: OSM footways only (204 line features in the 200 m box, ODbL, unofficial; e.g. a paved footway running past the north-west of the lot along (331541,6258842)-(331564,6258856)). No official footpath layer here.
- Street trees: none found. The only tree layers are Hornsby Shire Council's (wrong council); nothing in the box. Willoughby Council trees were not available. Survey needed.

## 6. Transport (straight-line distance from lot centre, official NSW Spatial Services, CC BY 4.0)
- **Chatswood Railway Station: 56 m** (331601.7, 6258853.1); about 36 m from the lot's NE corner. (Also Sydney Metro platforms at the same station.)
- Chatswood Bus Interchange: 138 m (331633.8, 6258931). Individual bus stops: only the interchange point is in the official dataset; no per-stop data.
- Tram: none (no tram layer or service here; Sydney's light rail does not reach Chatswood).
- Next stations: Artarmon 1,327 m; Roseville 1,493 m; Lindfield 2,699 m.

## 7. Winter solstice shadow study (21 June, AEST, flat-ground sun-ray calculation)
Sun (Chatswood, -33.797, 151.180): 9 am altitude 19.0 deg, azimuth 42.6 deg (NE); 12 noon altitude 32.8 deg, azimuth 359 deg (N); 3 pm altitude 18.1 deg, azimuth 316 deg (NW).
Method: each neighbouring OSM building extruded to its OSM height (not official), ray-cast from a 0.5 m grid over the lot toward the sun; the two buildings sitting on the lot were excluded. Ground slope ignored.

| Time | Lot in shadow of neighbours | Main casters |
|---|---|---|
| 9 am | ~77 percent (about 1,250 m2) | 26 m building to the east (elevated, min 9 m) dominates; 71 m north tower falls on the northern tip |
| 12 noon | ~62 percent (about 1,000 m2) | 71 m north tower shades the north part; 26 m east building the east edge; the south stays sunlit |
| 3 pm | ~99 percent (about 1,600 m2) | 87 m north-west tower (shadow ~160 m long) covers essentially the whole lot; lower west blocks minor |

Caveat: OSM footprints overlap the lot edges by a few metres, which overstates shading by the 26 m east building at 9 am. The existing on-site buildings would add their own shadow. Treat as indicative; redo with surveyed/council massing models.

## 8. Sources
| Data | Source / custodian | Year | Licence |
|---|---|---|---|
| Lot, area, boundary | NSW Spatial Services, Lots and properties (land parcel property theme), query lotidstring='1//DP724850', read 2026-11-08 | 2015 | CC BY 4.0 |
| Building footprints (official, no heights) | NSW Spatial Services, Building footprints | 2025 | CC BY 4.0 |
| Building heights/footprints (used for heights and shadows) | OpenStreetMap contributors via OpenFetch (osm-buildings-nsw), read 2026-11-08 | not stated | ODbL 1.0, not official |
| Building heights (LiDAR roof tops) | OpenFetch buildings (nsw-roofs) from NSW Spatial Services LiDAR 2020 and OSM/Microsoft outlines | 2020 | ODbL 1.0 / CC BY 4.0 |
| Zone, height, FSR, lot size | NSW Planning, Housing and Infrastructure, Willoughby LEP 2012 Amendment 34 maps | 2025 | CC BY 4.0 |
| Heritage | NSW Planning, Willoughby LEP 2012 heritage map | currency 2026 (year not stated) | CC BY 4.0 |
| Contours (ground levels) | NSW Spatial Services Elevation and Depth theme, Contour layer (2 m) | ~2009 | CC BY 4.0 |
| Spot heights (empty in box) | NSW Spatial Services | 2012 | CC BY 4.0 |
| Train station, bus interchange | NSW Spatial Services, Foundation Spatial Data transport facilities | year not stated | CC BY 4.0 |
| Footpaths | OpenStreetMap contributors via OpenFetch | not stated | ODbL 1.0, not official |
| Street trees (Hornsby Council, nothing in box) | Hornsby Shire Council | 2018/2019 | not stated |
| Sun position | Own calculation (standard solar algorithm) | 2026 | n/a |

OpenFetch data_used refs: du_qy66lq (lot), du_13q3js4 (footprints), du_nhd24y (zones), du_13i0i6d, du_1ha27lc, du_1b2n3hg (overlays), du_bmbj17 (heritage), du_xictox (spot), du_xcan5k (station), du_1xz1xvq (bus), du_19x6uwd (trees), du_1bxt4dc (OSM buildings), du_wlnxz7 (OpenFetch buildings). Credit: © State of NSW, CC BY 4.0; OpenStreetMap contributors, ODbL.
