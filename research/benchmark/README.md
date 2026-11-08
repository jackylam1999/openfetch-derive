# Suburb benchmark (game plan move 1)

Plan: `docs/handoffs/ahead-of-plain-ai.md` section 3, move 1. Measures OpenFetch's connector against a general AI assistant with web access on its own, on six ordinary sites, with one fixed prompt and a script that scores the answers. Results table: `docs/handoffs/suburb-bench-latest.md`.

**Rule (Jacky, 8 Nov 2026): no with/without run until the connector serves the same data as the app (parity).** The truth sheets and the scorer are built; the first run waits.

## Files
- `sites.json`: the six sites, busiest first by `tools/priority/TOP.md` where it fits: Hawthorn, Footscray, Preston (Jacky's picks), Chatswood, Parramatta, Geelong. Each is one lot inside the matching truth-site box of `tools/truth/` (Chatswood has none yet).
- `make-truth.mjs`: drafts `sites/<site>.json` straight from the official servers (Vicmap, NSW Spatial Services, NSW Planning Portal, the Geelong roofprints copy), never through the OpenFetch app or connector, so OpenFetch is not graded against itself. Re-run: `node research/benchmark/make-truth.mjs [site ...]`; it keeps the `checked` block.
- `sites/<site>.json`: one truth sheet per site: lot id, area, address, four lot corners and centre in MGA (GDA2020), tallest neighbour height (or "no official height published here"), zone and overlay codes at the lot centre, heritage overlay and grading, nearest station and distance, whether an official kerb dataset exists.
- `prompt.md`: the fixed prompt (the Peel St job with the address swapped). Never edit between runs.
- `score.mjs`: the scorer. `node research/benchmark/score.mjs --selftest` checks it; `node research/benchmark/score.mjs --write` scores every `runs/*.json` and rewrites the table.
- `runs/_example.json`: the run record format (files starting `_` are skipped).
- `runs/2026-11-08-peel-st-*.json`: the two Peel St trial runs (with and without), rebuilt from `research/peel-st-site-study/`, as the scorer's calibration. Peel St is not one of the six sites.

## Choices made while building (8 Nov 2026)
- Truth is read from the official servers directly, not with the connector's `get_layers` as brief BM1 says: the same Vicmap / NSW layers, but the benchmark cannot then inherit a connector bug as truth (the Peel St `find_site` lot bug is one). The by-eye check against the app on the same box (screenshot) is still the last step.
- Tallest neighbour within 100 m: only Geelong has an official building height (council roofprints). Vic metro has no open building LiDAR and NSW publishes no state building heights, so the other five say "no official building height published here"; an answer that calls an OpenStreetMap or estimated height official counts as wrong.
- Strata sites: when the lot point is common property (CM), any lot of the same plan counts as the right lot.
- Overlay areas and schedules count as the code: DDO61-A2 and "DDO61 (Area 2)" are DDO61.
- NSW sites have no Vicmap-style address in the sheet; the prompt uses the lot id there (`1//DP724850 Chatswood`).

## How a run is done (after parity)
1. Fresh session per run, model named in the record. Paste `prompt.md` with the address. Mode `with` = connector on; `without` = no connector, no OpenFetch site.
2. Three runs per site and mode (consistency needs at least two).
3. From the transcript, fill one `runs/<date>-<site>-<mode>-<n>.json` as in `_example.json`: what the answer said (not what is true), tool calls and minutes, which of the 15 reach items it gave, and every number it gave with its source stamp if it had one. Leave a fact `null` when the answer did not give it.
4. `node research/benchmark/score.mjs --write`, commit the run files and `docs/handoffs/suburb-bench-latest.md`.
Re-run after every connector milestone and monthly.

## The five scores
- **Truth**: count of wrong facts among lot id, area (2% or 2 m²), position (mean corner error over 1.0 m), zones, overlays, heritage, nearest station (name, distance within 15% or 50 m), official kerb yes/no, tallest neighbour (1.0 m, or claiming an official height where none is published). Also the position error and height error in metres.
- **Reach**: items given of the fixed 15: lot id, lot area, address, lot boundary, footprints, heights, height basis, zones, overlays, heritage, ground levels, kerbs, street trees, transport, shadows.
- **Cost**: tool calls and minutes.
- **Trace**: share of the numbers given that lead to a stamped source (`data_used` stamp or an equally exact dataset + date + query).
- **Consistency**: per site and mode, the count of facts that differ between runs (0 is the target).

Target (plan): truth errors 0 with the connector against 2 or more without; reach at least equal; cost at most half; consistency 0.

## Checking a truth sheet by eye
Open the lot in the Vicmap / NSW Spatial viewer and the planning scheme map, confirm lot id, area, zone, overlays, heritage and the station, then set `checked: {by: "<thread name>", on: "<date>", note}`. Credits name the source only (no personal names). Geoscape is never used.
