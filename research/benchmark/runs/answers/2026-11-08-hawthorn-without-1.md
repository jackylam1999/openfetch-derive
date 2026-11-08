Tool calls: 19, minutes: 8

# Site analysis: 23 Lynch Street, Hawthorn VIC 3122 (GDA2020 MGA Zone 55, levels AHD)

Several items could not be obtained; they are marked "not obtained". Overpass (OSM) and Geoscience Australia endpoints were blocked or timed out from this environment.

## 1. Lot and address
- Address (Vicmap Address, ezi_address): 23 LYNCH STREET HAWTHORN 3122; address point E 326936.6, N 5812176.5 (MGA55).
- Vicmap Parcel/Property polygon at that point: Lot 2 on Plan of Subdivision PS733527 (SPI 2\PS733527), property PFI 421833031, propnum 696410, LGA Boroondara. Area 1218 m2 (Shape area from the polygon).
- Caution: the polygon is a long thin strip, about 184 m east-west by about 6 m, which is unusual for a street address lot. Confirm against a title/certificate of title before relying on it.
- Boundary envelope (MGA55): NE [326981, 5812184], SE [326981, 5812173], SW [326797, 5812173], NW [326797, 5812184]. The true boundary is an irregular 20-vertex ring from Vicmap Parcel (e.g. 326937.7,5812173.8; 326797.5,5812179.3; 326802.7,5812184.4; 326981.2,5812174.0).

## 2. Buildings
Footprints: Vicmap Features of Interest Building Polygon (BUILDING_POLYGON, 2025 update). It has no height attribute.
| Building (Vicmap pfi) | Footprint extent E / N (MGA55) | Area m2 | Position | Height |
|---|---|---|---|---|
| 11935 | 326917-327009 / 5812147-5812175 | 2950 | immediately south of the lot | not obtained |
| 11956 | 326911-326933 / 5812085-5812135 | 1140 | about 40-90 m south | not obtained |
| 11862 | 326953-327050 / 5812214-5812272 | 5559 | about 35 m north-east (aquatic and leisure centre area) | not obtained |
| 11870 | 326745-326783 / 5812210-5812280 | 2222 | about 35-100 m north-west | not obtained |
No official building height was found, so I give no heights as fact. Official source for heights would be Victorian LiDAR/Vicmap Buildings (not accessed). For the shadow study treat any height as an estimate: assume 2 to 4 storeys (about 8 to 14 m) pending survey.

## 3. Planning
Source: Vicmap Planning (PLAN_ZONE, PLAN_OVERLAY), Boroondara Planning Scheme, queried at the address point.
- Zone: C1Z Commercial 1 Zone.
- Overlays on the lot: PO1 Parking Overlay Precinct 1; BFO2 Built Form Overlay Schedule 2; EAO Environmental Audit Overlay.
- Heritage: no heritage overlay at the lot. HO152 (Heritage Overlay) is mapped nearby, starting about 10 m north (N >= 5812188). Heritage grading (Boroondara Heritage Citation / Victorian Heritage Database): not obtained.
- SBO (Special Building Overlay) is mapped in the surrounding area but did not intersect the address point.

## 4. Ground levels (AHD)
Not obtained: the GA SRTM service was blocked and Vicmap Elevation is footprint-only in the service list. For a feasibility study order a point-cloud or 1 m DEM (DELWP/ELVIS LiDAR) and a feature survey. Rough expectation only (estimate, not data): Hawthorn centre slopes gently, roughly 35-45 m AHD, falling a metre or two across the lot.

## 5. Kerbs, footpaths, street trees
- Kerbs and footpaths: no official dataset obtained. Boroondara has asset data but I did not find an open kerb dataset; "official kerb dataset: not confirmed".
- Street trees: Vicmap Vegetation Tree Urban (2019 imagery, height from 2017-18 LiDAR) shows trees on and beside the strip, for example at E 326934.7, N 5812177.8 (height 33.5 m), 326945.2 / 5812176.7 (5.9 m), 326922.0 / 5812176.9 (6.6 m), 326963.8 / 5812177.5 (6.7 m), 326979.6 / 5812176.8 (8.7 m), and north at 326966.1 / 5812200.9 (13.5 m), 326977.7 / 5812201.6 (18.2 m), 326952.2 / 5812200.8 (14.4 m). These are modelled canopy trees, not council street-tree register entries.

## 6. Transport
- Nearest train station: Glenferrie Station (Lilydale/Belgrave/Alamein lines), about 200 m east (estimate, not measured from a verified coordinate).
- Tram: Glenferrie Road routes (route 16 and 72 area) on Glenferrie Rd, about 150-250 m east; bus stops on Glenferrie Rd and Burwood Rd. Stop-level distances not verified (PTV GTFS not accessed).

## 7. Winter solstice shadows (21 June, AEST, latitude -37.82, longitude 145.03; computed)
| Time | Sun altitude | Sun azimuth | Shadow direction | Shadow length per 10 m of height |
|---|---|---|---|---|
| 9 am | 12.6 deg | 46 deg (NE) | towards 226 (SW) | 44.6 m |
| 12 noon | 28.5 deg | 5.5 deg (N) | towards 185 (S) | 18.4 m |
| 3 pm | 18.3 deg | 322 deg (NW) | towards 142 (SE) | 30.3 m |
Reading: the building immediately south of the lot (11935) cannot shade it at any of these times because shadows fall away to the south. Shading comes from buildings to the north/north-east/north-west. The building to the north-east (11862, nearest corner about 35 m north and 15 m east) reaches the lot at 9 am if taller than about 11 m (needs 50 m of shadow along 226 degrees); at noon it needs about 19 m or taller (35 m / 18.4 per 10 m); at 3 pm it does not reach the lot (shadow falls SE, away). The north-west building (11870) can shade the western end at 12 noon and 3 pm only if above about 19 m (noon) or about 12 m (3 pm). With the assumed 8-14 m heights, expect 9 am shading of the lot from the NE building only if it is over about 11 m, and little at noon/3 pm. Heights are unverified, so this is conditional.

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| Vicmap Address (DEECA/DataVic) via ArcGIS FeatureServer, queried 2026-11-08 | current | CC BY 4.0 |
| Vicmap Parcel / Property (PARCEL_MP, PROPERTY_MP), same | current | CC BY 4.0 |
| Vicmap Planning PLAN_ZONE / PLAN_OVERLAY (zone gazetted 2026, overlays 2013-2026) | 2026 | CC BY 4.0 |
| Vicmap Features of Interest Building Polygon / Point | 2025 | CC BY 4.0 |
| Vicmap Vegetation Tree Urban (imagery 2019, heights 2017-18) | 2019 | CC BY 4.0 |
| Sun position computed (NOAA-style formulae) | 2026 | n/a |
