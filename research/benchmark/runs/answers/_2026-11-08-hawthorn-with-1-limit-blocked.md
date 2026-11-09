Tool calls: 15, minutes: 5

# Site analysis: 23 Lynch Street, Hawthorn VIC 3122 (GDA2020 MGA zone 55, EPSG:7855; levels AHD)

**Limits of this run.** The OpenFetch connector used its 20-requests-a-day limit part-way through (the second batch of data requests was refused). The open web (Overpass/OpenStreetMap) timed out from this environment. So items 4, 5, 6, 7 and building heights could not be fetched and are NOT answered with data below. I have not invented numbers.

## 1. Lot and address
- Address (Vicmap Address, 2026): 23 LYNCH STREET HAWTHORN 3122, address id 421833024. Address point E 326936.6, N 5812176.5.
- Lot: Lot 2 on PS733527 (SPI 2\PS733527), Vicmap Lots 2025. Area 759 m2 (area in the MGA grid, not the title area).
- The lot is a long thin strip, extent 183.8 m (E-W) by 11.8 m (N-S), 20 vertices. It sits on the boundary between the commercial strip and the transport (rail) corridor, so check title and the real boundary with a survey before relying on it.
- Extent corners (bounding box of the boundary, MGA55): NE [326981.2, 5812184.4], SE [326981.2, 5812172.6], SW [326797.5, 5812172.6], NW [326797.5, 5812184.4]. Centre of extent [326889.4, 5812178.5]. The boundary polygon itself is in the Vicmap lot data (not survey data).

## 2. Buildings and heights
Vicmap Building Footprints (2025, CC BY 4.0) in a 200 m box: 5 footprints, including one directly south, abutting the lot (about E 326916-327008, N 5812147-5812175), one at E 326911-326934, N 5812085-5812135, and one at E 326964-326985, N 5812075-5812118; larger ones north-east (E 326953-327049, N 5812214-5812272) and far away. **None has a height: height_basis = none for all.** So no official building height exists in this dataset here, and I give no tallest-neighbour height. OSM/Microsoft heights were not retrieved. For massing use a site survey, council 3D data or LiDAR.

## 3. Planning zone, overlays, heritage (Vicmap Planning, 2026, Boroondara planning scheme)
- Zones on the lot: Commercial 1 Zone (C1Z) over the southern part, and Transport Zone 1 State Transport Infrastructure (TRZ1) over the northern strip (the zone boundary runs along N about 5812179). Neighbours: PPRZ park to the north, TRZ2 and C1Z to the south.
- Overlays on the lot: PO1 Parking Overlay Precinct 1, BFO2 Built Form Overlay Schedule 2, EAO Environmental Audit Overlay.
- Not on the lot but nearby: HO152 (about 15 m north), HO261, HO24, HO262, HO491 (south/east, 30-100 m), SBO Special Building Overlay (north and south-west, not on the lot), BFO3 (east of the site).
- Heritage: no heritage overlay on the lot. Victorian Heritage Register H0516 Former ES&A Bank (Manresa Peoples Centre) is about 50 m south-east, VHR 2026, not on the lot. Victorian Heritage Inventory: nothing in the box. Council heritage grading (Boroondara) was not retrieved: not given.

## 4. Ground levels and fall
Not retrieved (request limit). Vicmap metro contours (2011) and spot heights are the official sources for this box; fetch them to get AHD levels. No figures given.

## 5. Kerbs, footpaths, street trees
Official kerb data: OpenFetch reports no kerb dataset for this box (none_here lists kerbs), so no official kerb dataset exists here that I could find. Street trees: Vicmap Vegetation Tree Urban (2021) and City of Boroondara Significant Trees (2026) exist for the box but were not retrieved. Footpaths come only from OpenStreetMap. Not answered.

## 6. Transport
Official timetable layers (Department of Transport and Planning, 2026) exist for train, tram and bus stops here, but I could not fetch them, so no distances are given. Glenferrie station is understood to be close, but I have not measured it and give no figure.

## 7. Winter solstice shadows
Not produced: no building heights were available, so no shadow outlines were drawn and no sun-angle figures are given.

## 8. Sources (all fetched via OpenFetch from the custodian)
| Source | Year | Licence |
|---|---|---|
| Vicmap Address (State of Victoria) | 2026 | CC BY 4.0 |
| Vicmap Lots (parcel_mp) | 2025 | CC BY 4.0 |
| Vicmap Building Footprints | 2025 | CC BY 4.0 |
| Vicmap Planning zones (PLAN_ZONE) | 2026 | CC BY 4.0 |
| Vicmap Planning overlays (PLAN_OVERLAY) | 2026 | CC BY 4.0 |
| Victorian Heritage Register / Heritage Inventory (DTP) | 2026 | CC BY 4.0 |
Read 2026-11-08, "Not survey data".
