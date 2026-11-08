Tool calls: 20, minutes: 6

# Site analysis: 59 Gheringhap Street, Geelong VIC 3220 (open data only)

Coordinates are GDA2020 MGA Zone 55 (EPSG:7855). Levels are AHD. Geometry was pulled from the Vicmap WFS (EPSG:7844) and converted by my own transverse Mercator code. Each MGA corner is good to about 0.1 m. The 6-decimal-degree rounding of the source leaves about 0.1 m of error.

## 1. Lot and address
- Address: 59 GHERINGHAP STREET GEELONG 3220 (Vicmap Address, property PFI 41077584). It is the only match on the register.
- Lot/plan: **Lot 1 TP821518** (SPI 1\TP821518), parcel PFI 4025858, status Active (Vicmap Property, parcel_view and v_parcel_mp).
- Area: **about 464 m2**. I computed this from the Vicmap parcel polygon in MGA. No area is attributed in the dataset, so check it against the title or a survey.
- Centre (vertex mean): E 268437, N 5774334.
- Boundary in MGA55, listed in order (the lot is a rotated 6-vertex polygon with a street frontage on Gheringhap Street):

| Corner (compass name) | E | N |
|---|---|---|
| W-most vertex (called NW) | 268421.4 | 5774330.8 |
| N-most vertex (called NE) | 268426.2 | 5774345.2 |
| mid-edge vertex | 268435.6 | 5774342.2 |
| E-most vertex (called SE) | 268455.1 | 5774335.6 |
| S-most vertex (called SW) | 268450.4 | 5774321.4 |
| mid-edge vertex | 268435.5 | 5774326.0 |

The lot is narrow and runs about 30 m by 15 m. Check the frontage orientation on site, because the compass labels are only the extreme vertices.

## 2. Buildings and heights
- The Vicmap Buildings polygon layer (open-data-platform:building_polygon) returned **no features** within roughly 250 m of the site, so I have no official footprints.
- I found **no official building heights** (Vicmap has no height attribute). Victoria's 1 m DEM (2007 coast LiDAR, Licensed) covers the area, but I could not download it here.
- OpenStreetMap via Overpass failed through the proxy, so no OSM footprints or heights were obtained either.
- The site is in the Geelong CBD and ACZ1 (Activity Centre Zone, Schedule 1), where neighbouring buildings are typically 2 to 10 storeys. I give no per-building heights. Treat any height as **none given**; commission a survey or obtain the council 3D model.
- Design controls on height are in DDO36 and ACZ1 Schedule 1 (Greater Geelong Planning Scheme). I did not read the schedule text, so confirm the height and setback limits there.

## 3. Planning (Vicmap Planning, Planning Scheme Zones and Overlays WFS, queried 2026-11-08 on the parcel polygon)
- Zone: **ACZ1**, Activity Centre Zone Schedule 1 (gazetted 2023-03-01). TRZ3 (Transport Zone 3, significant municipal road) touches the lot edge but is the road reserve, not the lot.
- Overlays on the lot: **DDO36** (Design and Development Overlay Schedule 36, 2015) and **HO1637** (Heritage Overlay).
- Heritage: HO1637 applies. I could **not** verify the heritage grading or citation. The Victorian Heritage Register layer returned nothing within 60 m. Check the Victorian Heritage Database, the Greater Geelong heritage study and the planning scheme HO schedule for the grading (grading: not obtained).

## 4. Ground levels (AHD)
- No site-scale spot levels were obtainable. Vicmap 10 m contours (el_contour) nearest the site are the 20 m AHD contour about 95 m to the west and the 10 m AHD contour much further east. This puts the site at **roughly 10 to 20 m AHD** (indicative only, not survey grade).
- The site is on the ground that slopes gently to the north-east, toward the Corio Bay waterfront. I could not quantify the fall on the lot. Order a feature and level survey, or use the 1 m Vicmap DEM (licensed) for 1 m levels.

## 5. Kerbs, footpaths, street trees
- I found **no official kerb dataset** in the Victorian open data catalogue. Vicmap has road centrelines and casement polygons only. No City of Greater Geelong kerb or footpath layer was found.
- Street tree data (Vicmap tree_urban, and a council tree register) returned nothing within 100 m. Not obtained. Survey on site.

## 6. Transport
- Nearest train station: **Geelong Station** (Vicmap rail_station point 144.354959, -38.144224; MGA55 E 268208, N 5774877), about **590 m** straight-line from the lot centre.
- Next station: Geelong South, about 1,040 m.
- Trams: Geelong has no tram network, so there are no tram stops.
- Bus stops: not obtained (PTV GTFS and OSM were not reachable). Gheringhap Street and the Moorabool Street / Malop Street corridor carry Geelong Transit bus routes. Confirm stop positions and distances in the PTV stop data.

## 7. Winter solstice shadows (21 June)
I did not model neighbour buildings because no footprints or heights were obtained. The sun position at the site (lat -38.149, lon 144.357), in AEST (UTC+10), is:

| Time | Sun altitude | Sun azimuth (from N) | Shadow direction | Shadow length per 1 m of height |
|---|---|---|---|---|
| 9 am | 12.0 deg | 47 deg (NE) | towards 227 deg (SW) | 4.7 m |
| 12 noon | 28.1 deg | 6 deg (about N) | towards 186 deg (S) | 1.9 m |
| 3 pm | 18.4 deg | 323 deg (NW) | towards 143 deg (SE) | 3.0 m |

Reading for design: buildings to the N, NE (9 am), NW (3 pm) and N (noon) of the lot cast onto it. A 20 m neighbour casts a shadow about 94 m long at 9 am, 37 m at noon and 60 m at 3 pm. Apply these ratios to surveyed heights to draw the shadow polygons. No site-specific shadow outline is given.

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| Vicmap Property (parcel_view, v_parcel_mp), DataVic WFS opendata.maps.vic.gov.au, queried 2026-11-08 | 2026 (UFI 2023) | CC BY 4.0, State of Victoria (DTP / DEECA) |
| Vicmap Address (address) | 2026 | CC BY 4.0 |
| Vicmap Planning (plan_zone, plan_overlay) | 2026 (overlay record 2026-03-26) | CC BY 4.0 |
| Vicmap Transport (vmlite_tr_rail_station) | 2021 | CC BY 4.0 |
| Vicmap Elevation contours (el_contour), 1 m DEM footprints | 2009 / 2007 | CC BY 4.0 (DEM files Licensed) |
| Vicmap Features (building_polygon, empty here) | n/a | CC BY 4.0 |
| Nominatim (OpenStreetMap) for the first geocode of the address | 2026 | ODbL |
| Solar position: own calculation | 2026 | n/a |
