Tool calls: 18, minutes: 5

# Site analysis: 147 Hopkins Street, Footscray VIC 3011
Grid: GDA2020 / MGA Zone 55 (EPSG:7855). Levels: AHD. All data read 2026-11-08 via the OpenFetch connector (no daily limit hit). Not survey data.

## 1. Lot and address
- Address (Vicmap Address, register match): 147 HOPKINS STREET FOOTSCRAY 3011 (address id 51591058). Address point E 315114.6, N 5814301.7. Council: Maribyrnong.
- Lot: **Lot 1 TP128421** (SPI 1\TP128421), status A. Area **181 m2** (area in the MGA grid, not the title area). Extent about 9.6 m (E-W) x 30.8 m (N-S). Centre E 315115.09, N 5814294.69.
- Extent corners (bounding box of the irregular lot, MGA 55): NE 315119.91, 5814310.11; SE 315119.91, 5814279.28; SW 315110.26, 5814279.28; NW 315110.26, 5814310.11.
- Boundary vertices (E, N): (315113.56, 5814280.87) (315112.96, 5814281.56) (315110.26, 5814284.68) (315110.65, 5814287.97) (315113.53, 5814310.11) (315119.91, 5814309.35) (315117.00, 5814286.67) (315116.91, 5814286.68) (315116.59, 5814284.14) (315116.48, 5814284.15) (315115.85, 5814279.28) (315114.72, 5814279.41) (315114.89, 5814280.84). It is a narrow, irregular lot.

## 2. Buildings and heights
Official footprint layers (City of Melbourne 2023, Vicmap building polygon) hold nothing in this box. Only OpenStreetMap footprints cover it (85 within the box plus 80 m north). Heights are OSM "stated" heights, not official; ground and top AHD come from Vicmap metro contours (2011, about +/-1 m, only where a contour vertex is within 30 m).
- On the lot: 3 OSM footprints, each 6 m (OSM stated).
- Around the site (within about 100 m): almost all are 6 m (mostly 2 storeys). The tallest within 100 m is **9 m** (3 storeys, OSM stated) at about E 315092, N 5814214, roughly 84 m south-south-west; ground 19 m, top 28 m AHD. Others within 100 m: 6 m (ground 19-20 m, top 25-26 m AHD).
- Further out: one 12 m (4 storey) building near E 315047, N 5814464 (about 170 m NNW), OSM stated.
- Treat all as estimates: OSM heights are volunteer-entered and the uniform 6 m looks like a 2-storey default.

## 3. Planning (Vicmap Planning, 2026, CC BY 4.0)
- Zone: **ACZ1** Activity Centre Zone, Schedule 1 (Maribyrnong). The adjoining road is TRZ3.
- Overlays on the lot: **PO1** Parking Overlay Precinct 1; **DCPO2** Development Contributions Plan Overlay Schedule 2; **HO3** Heritage Overlay (HO3).
- Heritage: HO3 applies to the lot. Nearby but not on the lot: HO57, HO199, HO202. No Victorian Heritage Register or Heritage Inventory record in the box. I could not get a property grading (A/B/C etc.): the graded-property layer is City of Melbourne only, not Maribyrnong. Check the Maribyrnong heritage citation for HO3 for the grading.

## 4. Ground levels
Vicmap metro contours (2011, 1 m interval): the lot sits between the 20 m contours running just south (E 315115-315221, N ~5814257-5814279) and west (E 315067-315079); 19 m contour about 70 m south (N ~5814226); 21 m contour about 140 m north (N ~5814436). Ground is about 20 m AHD (20-21), falling roughly 1 m over about 70 m to the south: very gentle. No LiDAR or survey data used; get a survey for levels.

## 5. Kerbs, footpaths, street trees
- Kerbs: official Maribyrnong City Council kerb line dataset exists (road asset register, 2026-09-30, CC BY 2.5 Australia, not yet quality-profiled): nearest Maddern Square seg 01 (asset 56868, about 20 m), Hopkins Street seg 06 Nicholson-Leeds (56678, about 23 m), Hopkins Street seg 01 (56673, about 33 m); 20 kerb polygons in the box.
- Footpaths: Maribyrnong footpath register: Hopkins Street seg 06 (asset 70063, about 20 m), seg 01 (70050, about 33 m), Maddern Square (142930, about 39 m).
- Street trees: Vicmap Vegetation Tree Urban (2021): none on the frontage in the 150 m box. Nearest: E 315079, N 5814312 (height 15.6 m, canopy radius 8.4 m, about 40 m west); E 315067, N 5814246 (15.2 m, r 6.0 m); E 315079, N 5814343 (12.1 m); E 315060, N 5814330 (9.3 m). Note the 2021 layer is dated.

## 6. Transport (straight line from lot centre)
- Nearest train: **Footscray Railway Station** (Metro and V/Line), **235 m** (E 315297.5, N 5814146.5). Then Middle Footscray 798 m, Seddon 1065 m.
- Tram: Nicholson St/Hopkins St #62, 31 m; Leeds St/Hopkins St #63, 85 m; Footscray Market/Leeds St #63, 94 m.
- Bus: Hopkins St/Leeds St 94 m; Nicholson St/Droop St 97 m; Nicholson St/Paisley St 108 m.

## 7. Winter solstice shadows (21 June, AEST, flat ground, OSM heights)
Computed with my own ray test over 727 sample points in the lot, ignoring the 3 buildings on the lot. Sun: 9 am altitude 12.6 deg, azimuth 46 deg (shadows fall SW); 12 noon 28.5 deg, azimuth 6 deg (shadows fall south); 3 pm 18.4 deg, azimuth 322 deg (shadows fall ESE).
- 9 am: about 56% of the lot shaded by neighbours (6 m buildings cast about 27 m).
- 12 noon: 0% shaded (6 m casts about 11 m; the buildings to the north are far enough away or low).
- 3 pm: about 8% shaded (6 m casts about 18 m).
Caveat: heights are OSM estimates; the buildings on the lot are assumed to be removed; no trees included.

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| Vicmap Address, State of Victoria | 2026 | CC BY 4.0 |
| Vicmap Lots (parcel_mp), State of Victoria | 2025 | CC BY 4.0 |
| Vicmap Planning zones and overlays | 2026 | CC BY 4.0 |
| OpenStreetMap buildings via OpenFetch (NOT OFFICIAL) | read 2026-11-08 | ODbL 1.0 |
| Vicmap metro contours | 2011 | CC BY 4.0 |
| Vicmap Vegetation Tree Urban | 2021 | CC BY 4.0 |
| Maribyrnong City Council kerbs and footpaths | 2026-09-30 | CC BY 2.5 Australia |
| Dept of Transport and Planning train, tram, bus stops (hosted copy) | 2026 | CC BY 4.0 |
| City of Melbourne building footprints and heritage; Vicmap building polygon; Heritage Inventory (searched, nothing here) | 2023 / 2026 | CC BY 4.0 |
Data-used stamps are available from the OpenFetch calls (read 2026-11-08); I did not call make_appendix.
