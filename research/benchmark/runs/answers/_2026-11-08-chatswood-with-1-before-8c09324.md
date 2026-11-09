Tool calls: 19, minutes: 6

# Site analysis: 1//DP724850, Chatswood (Willoughby LGA)

Coordinates GDA2020 / MGA Zone 56 (EPSG:7856), levels AHD. This is a partial analysis. The OpenFetch connector and the open web gave the lot, zone and height control. They did not give building heights, ground levels, kerbs, a heritage listing or stops, so those sections are gaps, not "nothing there". Not survey data; verify before design use.

## 1. Lot
- Lot 1 DP 724850 (lotidstring 1//DP724850). Source: NSW Spatial Services cadastre (Lot layer, maps.six.nsw.gov.au NSW_Cadastre MapServer/9), queried 2026-11-08. The OpenFetch parcel layer is dated 2015.
- Area: 1,617 m2 (planlotarea 1617.006). The polygon vertices give 1,609 m2 by shoelace, so use 1,617 m2 as the registered area.
- Boundary (MGA56, 11 main vertices, in metres):
  - NE 331565.27, 6258850.76
  - SE 331584.07, 6258778.24
  - SW 331566.38, 6258771.29
  - NW 331541.92, 6258841.55
  - Other vertices: (331572.50, 6258817.83), (331583.52, 6258784.72), (331578.75, 6258776.15), (331556.21, 6258804.00), (331549.82, 6258816.09), (331545.10, 6258831.52)
- Centroid (vertex mean): E 331562.7, N 6258810.5 (about lat -33.79749, lon 151.18047).
- Street address: not obtained. OpenFetch find_site needs a street number and the address service query failed, so I have no address to give.

## 2. Buildings and heights
- The official footprints (NSW Spatial Services building footprints, 2025, CC BY 4.0) return only points for this box, with no heights (height_basis "none"). One point is at 331537.75, 6258801.21, west of the lot. Others are at 331428.57, 6259025.64 and 331530.22, 6258996.99.
- No official building height is available. OpenStreetMap (Overpass) timed out, so no OSM heights either.
- Tallest neighbour: no height given. No height of any neighbouring building is stated.
- The nearest thing to a height is the LEP control in section 3: a maximum of 246.8 m RL. It is a planning limit, not an existing building.

## 3. Planning (Willoughby LEP 2012, Amendment 34; NSW Planning Portal EPI layers, currency 2026, CC BY 4.0)
- Zone: E2 Commercial Centre.
- Height of Buildings map: 246.8 m RL (class ">100 m").
- Floor space ratio, lot size and land reservation acquisition: no mapped feature intersecting the lot. This may be a gap in the layers rather than "no control", so check the FSR map.
- Heritage map (LEP): no item or conservation area intersects the lot. No heritage grading found; I did not check the State Heritage Register or council inventory.
- OpenFetch TOD (Housing SEPP) layer: empty here.
- Overlays: only the height of buildings map has a value. I did not check flood, bushfire or acid sulfate soils on the lot.

## 4. Ground levels
Not obtained. The official spot heights (2012) cover the box but hold nothing, and no contours or DEM were returned. Commission a survey, or pull the NSW 1 m DEM / ELVIS LiDAR.

## 5. Kerbs, footpaths, street trees
OpenFetch has no kerb, footpath or tree data for this box; I found no official kerb dataset here. The Hornsby tree layer listed does not cover Willoughby. Needs a site survey.

## 6. Transport
I could not fetch official stop data. From general knowledge, Chatswood station is very close, roughly 90 m from the lot centre (approximate, unverified). I have no verified tram or bus stop distances. There is no tram in Chatswood. Bus stops are at the Interchange, nearby.

## 7. Shadows (21 June)
Not done: there are no building heights, so a study would be invented. Sun at Chatswood, lat -33.8, on 21 June, from standard solar geometry: noon altitude about 32.7 degrees, so a shadow is about 1.55 times height. At 9 am and 3 pm the altitude is about 17 to 18 degrees, so a shadow is about 3.1 times height (the connector hint gives 1.6 and 3.1). To model the shadow from the neighbours, get their heights from survey or LiDAR first.

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| NSW Spatial Services cadastre, Lot layer (SIX maps) | current (read 2026-11-08) | CC BY 4.0 |
| OpenFetch parcels, six-nsw-land-parcel-property-theme-multicrs-8 | 2015 | CC BY 4.0 |
| OpenFetch footprints, six-nsw-features-of-interest-category-multicrs-3 | 2025 | CC BY 4.0 |
| OpenFetch spot heights, six-nsw-elevation-and-depth-theme-multicrs-0 | 2012 | CC BY 4.0 |
| NSW Planning Portal EPI Primary Planning Layers (Willoughby LEP 2012) | 2026 currency | CC BY 4.0 |
| OpenFetch TOD sites, epi-planning-portal-sepp-752 | 2026 | CC BY 4.0 |

Data-used stamps are in the OpenFetch answers (refs du_xk9xl2, du_lt9gis, du_y8ihrg, du_dtebat, du_adqvaj). I did not call make_appendix.
