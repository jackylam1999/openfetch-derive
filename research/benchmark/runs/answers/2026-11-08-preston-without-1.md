Tool calls: 27, minutes: 14

# Site analysis: 24 Arthur Street, Preston VIC 3072 (open web only)

Coordinates are GDA2020 MGA zone 55 (EPSG:7855). Levels are AHD. Many official Victorian services (services.land.vic.gov.au, Planning Maps, Darebin GIS) were blocked from this environment. The Vicmap data below came from the DEECA "Vicmap_Prod" hosted ArcGIS services, which republish the official Vicmap layers. Where I could not get official data I say so. I did not get official building heights, 1 m terrain, kerb data or street-tree data.

## 1. Lot and address
- Address: 24 ARTHUR STREET PRESTON 3072 (Vicmap Property Address, source code LGO, class S). OSM also has an address node for it at about -37.74303, 144.99955.
- Lot and plan: Lot 23 on LP7668 (parcel_spi "23\LP7668"). Parcel PFI 175992, property number 184951, Darebin LGA (316).
- Area: 574 m2. I calculated this from the Vicmap Property polygon in MGA 55, as a planar area with no grid-scale correction. It is not the title area. Check the title or survey before relying on it. The service's own Shape__Area field (919.6) is in Web Mercator and is not a ground area.
- Boundary vertices (MGA 55, E, N), in order:
  - NE (323777.4, 5820817.3)
  - extra east-boundary vertex (323778.1, 5820813.7)
  - SE (323780.5, 5820802.8)
  - SW (323738.9, 5820807.2)
  - NW (323737.6, 5820821.5)
- Centre (vertex mean): about (323762.5, 5820812.5).
- Shape: the lot is about 41 m deep east-west and 11 to 14 m wide. Arthur Street runs roughly north-south just west of the lot, so the frontage is the west boundary, about 14.3 m (NW to SW).

## 2. Buildings and heights
Footprints are from OpenStreetMap (ODbL), fetched through Overpass. No official Victorian building-height dataset was reachable, and the OSM footprints carry no height or level tags. Every height below is my estimate from the OSM building type. They are not measurements.

- On the lot: OSM way 615679959, detached house, about 172 m2. Estimated 4.5 m high (single storey plus roof). Estimate.
- North, 18 m from the lot centre: way 615679958, "apartments", 258 m2. Estimated 9.5 m (3 storeys). Estimate.
- South, 15 m: way 615679960, detached house, 250 m2. Estimated 4.5 m. Estimate.
- 49 m south-east: way 615679963, apartments, 132 m2. Estimated 9.5 m. Estimate.
- 71 m: way 615679954, apartments, 267 m2. Estimated 9.5 m. Estimate.
- 98 m: way 615679955, apartments, 488 m2. Estimated 9.5 m. Estimate. This is the tallest neighbour within 100 m, and the height is an estimate.
- All other buildings within about 110 m are detached houses or garages. I assumed 4.5 m for houses and 2.7 m for garages. OSM has 51 footprints in this area.
- Height basis for all of the above: estimate only. Confirm with a survey or LiDAR/ELVIS data before design use.

## 3. Planning
Source: Vicmap Planning, PLAN_ZONE and PLAN_OVERLAY (DEECA, via Vicmap_Prod). I sampled the whole lot against the polygons.
- Zone: HCTZ2, Housing Choice and Transport Zone, Schedule 2, covering 100% of the lot. Gazetted 2025-04-11. A TRZ1 polygon (Transport Zone 1) also touches the lot's bounding area, but it does not cover the lot.
- Overlays on the lot, each covering 100%:
  - DCPO1: Development Contributions Plan Overlay, Schedule 1.
  - ICO1: Infrastructure Contributions Overlay, Schedule 1.
  - HO186: Heritage Overlay, "Preston War Service Homes precinct".
- Heritage: HO186 is a precinct overlay. The Darebin Planning Scheme Clause 43.01 schedule (version C161, 2021) lists it as "17-25 & 18-28 Arthur Street, 27-37 Bruce Street, 1-9 & 10-16 Herbert Street...". That includes number 24. I did not find an individual grading (such as contributory or non-contributory) for number 24. Check the Darebin Heritage Study citation (Preston Central, Volume 4b) or ask Council's heritage officer.
- The zone is new (April 2025) and the overlay set may have changed since. Confirm with a Council planning property report (the Planning Property Report from Planning Victoria's Planning Maps Online) before relying on this.

## 4. Ground levels (AHD)
- Source: Vicmap Elevation 1:25,000 (10 m contour interval) and spot heights. This is coarse.
- The 60 m AHD contour passes about 11 m from the lot (at about 323766, 5820819). So the lot sits at about 60 m AHD, plus or minus 5 m.
- Regional fall: the 70 m contour is about 500 m away to the north-east and north-west. The 50 m contour is about 1.2 km to the south-west. The general fall is downhill to the south and south-west, at roughly 1 in 50 to 1 in 100.
- I did not get lot-scale levels (1 m LiDAR or survey). The fall across the 41 m lot is not known from this data. Commission a feature and level survey.

## 5. Kerbs, footpaths and street trees
- OSM shows Arthur Street as a residential road with separate footways on both sides (ways 1066705266 and 1066705268, unverified). There are laneways at the north and south.
- Kerbs: no official council or government kerb dataset was found or reachable, and OSM has no kerb lines here. Not available from my sources.
- Street trees: none are mapped in OSM within 60 m. I could not reach a Darebin street-tree dataset. A site visit is needed.

## 6. Transport (straight-line distance from the lot centre)
- Nearest train station: Bell Station, 334 m. Preston Station is 482 m. Both are on the Mernda line (OSM station nodes).
- Nearest bus stops:
  - Bruce Street/St Georges Road, 100 m.
  - NMIT Preston Campus/St Georges Road, 137 m.
  - Bell Station/Bell Street, 211 m.
  - St Georges Road/Bell Street, 299 m.
- Nearest tram stops: Stop 45 Bell Street, 647 m. Stop 44 Seymour Street/Osborne Grove, 668 m. Stop 47 David Street, 743 m.
- Source: OpenStreetMap, including the PTV stop references on bus stops. I did not use the official PTV GTFS feed.

## 7. Winter solstice shadow study (21 June, AEST)
Method: sun position at -37.743, 145.000 on the solstice (declination +23.44 degrees). Shadows are cast by the OSM footprints at my estimated heights, excluding the building on the lot. I sampled the lot on a 0.5 m grid.

| Time (AEST) | Sun elevation | Sun azimuth | Shadow length, 4.5 m house | Shadow length, 9.5 m building | Lot shaded by neighbours |
|---|---|---|---|---|---|
| 9 am | 12.9 degrees | 46 degrees (north-east) | 19.7 m | 41.6 m | about 53% |
| 12 noon | 28.6 degrees | 5 degrees (north) | 8.2 m | 17.4 m | about 59% |
| 3 pm | 18.2 degrees | 322 degrees (north-west) | 13.7 m | 28.9 m | about 68% |

- The main shading comes from the north: the 3-storey apartment building (way 615679958) and houses on the lots to the north and south.
- All percentages depend on the estimated heights. If the real heights differ, the results change roughly in proportion.
- Because the lot is deep east-west and narrow, the neighbours' long boundary walls dominate at 9 am and 3 pm.
- Sun times use a longitude correction only. I ignored the equation of time (about 2 minutes).

## 8. Sources
| Source | Year | Licence |
|---|---|---|
| Vicmap Property, Parcel and Address (DEECA, via Vicmap_Prod hosted ArcGIS services, queried 2026-11-08) | current (to 2026) | CC BY 4.0 (Victorian Government) |
| Vicmap Planning PLAN_ZONE and PLAN_OVERLAY (same service, 2026-11-08) | current (zone gazetted 2025) | CC BY 4.0 |
| Vicmap Elevation 1:25,000 contours and spot heights (same service) | current | CC BY 4.0 |
| Darebin Planning Scheme, Clause 43.01 Heritage Overlay schedule (version C161; planning.vic.gov.au) | 2021 | State of Victoria; Creative Commons Attribution |
| OpenStreetMap via Overpass (maps.mail.ru mirror): buildings, streets, stops, stations | 2026 | ODbL 1.0 |
| Nominatim geocoder (OpenStreetMap) for the address node | 2026 | ODbL 1.0 |
| Own sun-angle and shadow calculation (node.js) | 2026 | not applicable |

Licences are as I understand them for these datasets. I did not read each licence page.

## Gaps
- Official building heights, lot-scale levels, kerb lines and street trees were not obtained.
- The heritage grading for number 24 was not obtained.
- Title area and lot dimensions need a title search or survey.
