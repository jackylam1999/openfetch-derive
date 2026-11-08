Tool calls: 22, minutes: 6

# Site analysis: 147 Hopkins Street, Footscray VIC 3011

All coordinates are GDA2020 MGA Zone 55 (EPSG:7855), converted by me from the GDA2020 lon/lat that Vicmap serves. Levels are AHD. Data came from Vicmap public WFS (opendata.maps.vic.gov.au). Several items could not be sourced; they are marked as gaps.

## 1. Lot and address
- Address (Vicmap Address): 147 HOPKINS STREET FOOTSCRAY 3011, address point E 315114.6, N 5814301.7 (lon 144.89999, lat -37.799965). Property PFI 1096954, council property number 115096, Maribyrnong LGA (341).
- Lot: Lot 1 on Title Plan 128421 (SPI 1\TP128421), parcel PFI 1096954 (Vicmap Parcel, v_parcel_mp).
- Area: about 182 m2, computed by me from the Vicmap polygon in MGA55. Vicmap parcels are not survey accurate, so check against the title.
- Shape: a narrow, long lot. About 10 m wide at the Hopkins Street (north) end, narrowing to about 1 m dog-leg at the south end. About 31 m long, running roughly north-south.
- Boundary vertices (MGA55 E, N): extent corners NE 315119.93, 5814309.38; SE 315115.85, 5814279.31; SW 315114.71, 5814279.40; NW 315113.49, 5814310.12. Centre (vertex mean) 315114.9, 5814287.4. Full ring (E, N): (315113.53, 5814280.82), (315112.98, 5814281.58), (315110.27, 5814284.63), (315110.64, 5814287.97), (315113.49, 5814310.12), (315119.93, 5814309.38), (315117.01, 5814286.67), (315116.63, 5814284.10), (315115.85, 5814279.31), (315114.71, 5814279.40), back to start.

## 2. Buildings and heights
- Vicmap Features of Interest building_polygon has almost no coverage here: only 1 footprint within about 500 m of the site (at 144.8964, -37.8037), and none on or beside the lot. It carries no height attribute anyway.
- I found no official building footprints or building heights for the site or its neighbours. I did not estimate heights. No tallest-neighbour height is given.
- The Overpass (OpenStreetMap) service was blocked from my environment, so I could not pull OSM footprints or heights.
- What I can say: Hopkins Street addresses 141-151 (odd side, south) and 142-154 (even side, north) are within about 30 m of the lot, and the zone (ACZ1) allows mid-rise built form, but I have no measured heights.
- Gap: you need a footprint and height source (Geoscape Buildings, council 3D model, or field survey).

## 3. Planning zone, overlays, heritage (Vicmap Planning, Maribyrnong Planning Scheme)
- Zone: ACZ1 Activity Centre Zone, Schedule 1 (gazetted 2015-03-19).
- Overlays at the lot point: HO3 Heritage Overlay (HO3); DCPO2 Development Contributions Plan Overlay Schedule 2; PO1 Parking Overlay Precinct 1.
- Heritage: Heritage Overlay HO3 applies. I did not find the individual heritage grading (contributory / non-contributory) for number 147; check the Maribyrnong heritage citation or the Victorian Heritage Database. Grading: not found.
- The point query returned only these three overlays. Check the planning certificate for DDO or others.

## 4. Ground levels (AHD) and fall
- No spot heights or DEM were reachable. The only data was the Vicmap 1-5 m contours (el_contour_1to5m): the 20 m (index) contour passes about 27-30 m from the lot centre and a 19 m contour about 72 m away, a 21 m contour about 130 m away. So ground at the lot is roughly 19-21 m AHD, about 20 m AHD, with a gentle regional fall, but I cannot give a measured fall across the lot (under about 1 m expected). Treat as indicative only; commission a feature survey.

## 5. Kerbs, footpaths, street trees
- Kerbs and footpaths: I did not find an official council or government kerb/footpath dataset, and none is stated here.
- Street trees: Vicmap Urban Tree (tree_urban, canopy-derived from 2017-19 LiDAR/imagery) shows trees near the frontage, no council inventory. Nearest: 21 m from the lot centre at E 315126.2, N 5814269.9 (height 13.5 m, canopy radius 5.1 m); also 37-54 m away at (315141.4, 5814261.3) 13.0 m, (315151.4, 5814267.3) 11.7 m, (315152.4, 5814260.8) 13.2 m, (315158.5, 5814260.7) 13.6 m, (315163.1, 5814262.9) 14.5 m; west side (315079.2, 5814312.1) 15.6 m, (315067.4, 5814246.5) 15.2 m. These are canopy points, not confirmed street trees. Council street-tree register not checked.

## 6. Transport
- Nearest train station: Footscray Station, about 308 m (straight line from the address point to the Vicmap station point, E/lon 144.9032, lat -37.801072). Next nearest Flemingington Racecourse is about 1.57 km.
- Tram and bus stops: not measured (no PTV GTFS stop data was pulled). Footscray has bus services around the station and Hopkins Street, and tram route 82 ends in Footscray, but I give no stop distances.

## 7. Winter solstice shadows (21 June)
Sun position computed for lat -37.80, lon 144.90, AEST (UTC+10):

| Time | Altitude | Azimuth (from N) | Shadow direction | Shadow length per 1 m height |
|---|---|---|---|---|
| 9 am | 12.6 deg | 46 | SW (226) | 4.48 m |
| 12 noon | 28.5 deg | 6 | S (186) | 1.84 m |
| 3 pm | 18.4 deg | 322 | SE (142) | 3.01 m |

Because no neighbour heights were available, I did not draw shadow polygons. For the lot (frontage on the north, long axis north-south), a building on the north side of Hopkins Street of height H casts a shadow toward the site: at noon the shadow reaches 1.84 H south of its south face. At 9 am shadows cast from the NE and at 3 pm from the NW, so the lot is mostly shaded from the north and its long narrow shape means a 3-storey (about 10 m) neighbour to the north would shade the full 31 m depth only if H greater than about 17 m at noon. Supply heights to complete the study.

## 8. Sources
| Source | Year / date | Licence |
|---|---|---|
| Vicmap Address (address) | queried 2026-11-08; ufi created 2023 | CC BY 4.0 (State of Victoria, DEECA/DTP) |
| Vicmap Property / Parcel (v_parcel_mp, v_property_mp, parcel_property) | queried 2026-11-08; parcel updated 2024-02 | CC BY 4.0 |
| Vicmap Planning (plan_zone, plan_overlay) | queried 2026-11-08; ufi created 2024-2026 | CC BY 4.0 |
| Vicmap Features of Interest (building_polygon) | queried 2026-11-08 | CC BY 4.0 |
| Vicmap Elevation contours (el_contour_1to5m) | 2011 contour records | CC BY 4.0 |
| Vicmap Urban Tree (tree_urban) | imagery 2019, heights 2017-18 | CC BY 4.0 |
| Vicmap Lite rail station (vmlite_tr_rail_station) | 2021 | CC BY 4.0 |
| Own calculations: area, MGA conversion, sun position (NOAA solar equations) | 2026 | n/a |
