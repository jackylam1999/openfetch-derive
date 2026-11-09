Tool calls: 21, minutes: 4

# Site analysis: 147 Hopkins Street, Footscray VIC 3011
Grid: GDA2020 MGA Zone 55 (EPSG:7855); levels AHD. All data is "not survey data"; check before design use.

## 1. Lot and address
- Address (Vicmap Address 2026): 147 HOPKINS STREET FOOTSCRAY 3011 (address point E 315114.6, N 5814301.7).
- Lot: Lot 1 TP128421 (SPI 1\TP128421), Vicmap Lots 2025, area 181 m2 (area in the MGA grid, not the title area). Council: Maribyrnong.
- Corners (lot vertices): NE 315119.91, 5814309.35; SE 315115.85, 5814279.28; SW 315114.72, 5814279.41; NW 315113.53, 5814310.11. Centre (extent middle) 315115.09, 5814294.69. The lot is a narrow strip (~6 m x 31 m extent, 9.6 x 30.8 m box) with a dog-leg on its west side; full 14-vertex boundary is in the find_site answer (boundary_mga).

## 2. Buildings (heights)
- Official footprints: Vicmap Building Polygon (2025) and City of Melbourne 2023 returned nothing in this box. Only OpenStreetMap footprints (ODbL, not official) exist here: 68 buildings in a 150 m box.
- Height basis: OpenStreetMap "stated" (height tag / 2 levels = 6 m); the near-identical 6 m values look like a default for 2-storey buildings, so treat as estimates +-3 m. Ground from Vicmap metro contours (2011, about +-1 m), 19-20 m AHD, so tops about 25-26 m AHD where computed (many have no ground within 30 m).
- On the lot: OSM building centred 315113.8, 5814293.5, 6 m (2 levels), OSM stated.
- Around (within 100 m): ~55 buildings of 6 m (OSM, 2 levels), 3 with no height. Tallest within 100 m: 9 m (3 levels, top 28 m AHD, ground 19), at 315091.8, 5814214.5, about 84 m SSW, OSM stated. Nearest neighbours: 6 m at 315107.4, 5814297.6 (8 m W), 315121.5, 5814286.2 (11 m, 20 m AHD ground, top 26), 315128.2, 5814291.5 (13 m E).

## 3. Planning
Source: Vicmap Planning 2026 (CC BY 4.0), overlays read as polygons containing the lot.
- Zone: ACZ1 Activity Centre Zone, Schedule 1.
- Overlays on the lot: PO1 (Parking Overlay Precinct 1), DCPO2 (Development Contributions Plan Overlay Schedule 2), HO3 (Heritage Overlay).
- Heritage: HO3 applies to the lot. A property grading (e.g. contributory/significant) was not available: City of Melbourne gradings do not cover Maribyrnong, and the Victorian Heritage Register and Heritage Inventory have nothing in the box. Check the HO3 schedule and the Maribyrnong heritage citation for the grading. Nearby but not on the lot: HO57, HO199, HO202.

## 4. Ground levels
Vicmap metro contours (2011, 1 m interval): 20 m AHD contour passes ~10-40 m west and south of the lot, 19 m about 60-75 m south; the lot sits at about 20 m AHD with a fall of up to about 1 m (to ~19-20 m) towards the south. Effectively flat; a site survey is needed for finer levels. No lidar/DEM was fetched.

## 5. Kerbs, footpaths, trees
- Official council data exists: Maribyrnong City Council asset registers (2026-09-30), kerb lines (Hopkins St Seg 01 and Seg 06 Nicholson-Leeds, 23-33 m from the site centre), and footpaths (Hopkins St Seg 01 and 06, 20-36 m). Kerbs are polygons, footpaths lines (position only, no widths/levels). 17 kerb features and 15 footpath features in the 150 m box.
- Trees: Vicmap Vegetation Tree Urban (2021), 11 trees in the box, 5-16 m high; nearest 315126.2, 5814269.8 (27 m, 13.5 m high, canopy r 5 m), 315079.2, 5814312.1 (40 m, 15.6 m), 315141.3, 5814261.3 (42 m). These are canopy trees, not a council street-tree inventory.

## 6. Transport (straight line from site centre)
- Train: Footscray Station 235 m (E 315297.5, N 5814146.5; Metro and V/Line). Then Middle Footscray 798 m, Seddon 1065 m.
- Tram: Nicholson St/Hopkins St #62, 31 m; Leeds St/Hopkins St #63, 85 m; Footscray Market/Leeds St, 94 m.
- Bus: Hopkins St/Leeds St 94 m; Nicholson St/Droop St 97 m; Nicholson St/Paisley St 108 m.

## 7. Winter solstice shadows (21 June, AEST, my calculation)
Method: sun position for latitude -37.8, longitude 144.9, equation of time -1.7 min; shadows from OSM building footprints at their stated 6 m (9 m for one) cast on the lot, excluding the building on the lot itself. Heights are estimates, so results are indicative.
- 9 am: sun altitude 12.5 deg, azimuth 46.5 deg (NE); shadows run SW at 4.5 m per metre of height; about 56% of the lot is shaded by the neighbours.
- 12 noon: altitude 28.5 deg, azimuth 6 deg (N); 1.84 m per metre; neighbours cast no shadow onto the lot (0%); the lot's north neighbours are too far/low.
- 3 pm: altitude 18.4 deg, azimuth 322 deg (NW); 3.0 m per metre; about 11% shaded.
Note the existing building on the lot and any taller new neighbours are not included.

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| Vicmap Address | 2026 | CC BY 4.0 |
| Vicmap Lots (parcel) | 2025 | CC BY 4.0 |
| Vicmap Planning zones and overlays | 2026 | CC BY 4.0 |
| Vicmap Elevation metro contours | 2011 | CC BY 4.0 |
| Vicmap Vegetation Tree Urban | 2021 | CC BY 4.0 |
| Maribyrnong City Council kerb and footpath asset registers | 2026 | CC BY 2.5 Australia |
| DTP Transport Victoria timetable stops (train, tram, bus) | 2026 (weekly) | CC BY 4.0 |
| Vicmap Building Polygon; City of Melbourne footprints; Microsoft footprints (all empty here) | 2025/2023 | CC BY 4.0 / ODbL |
| OpenStreetMap buildings (via OpenFetch) | not stated | ODbL 1.0 (not official) |
| VHR / Heritage Inventory (nothing in box) | 2026 | CC BY 4.0 |
All read via OpenFetch on 2026-11-08, no daily limit reached. Not survey data.
