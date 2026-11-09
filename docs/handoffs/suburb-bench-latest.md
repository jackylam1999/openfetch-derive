# Suburb benchmark: latest scores

Made by `node research/benchmark/score.mjs --write` (method: `research/benchmark/README.md`; plan: `ahead-of-plain-ai.md` move 1). The first with/without run waits for connector parity (Jacky, 8 Nov 2026). Not the same file as `bench-latest.md`, which is the app speed bench (`tools/bench-e2e.js`).

Peel St rows are the 8 Nov 2026 trial rebuilt from its notes (calibration), not a benchmark run.

## Truth sheet check (8 Nov 2026)

Not yet checked against the app: app-preview.openfetch.earth is blocked from the cloud session (network policy, proxy 502), so no screenshot comparison was possible. The `checked` block in each sheet is left unset on purpose.

What was done instead: all six sheets were rebuilt from the official servers into a scratch copy and compared with the committed ones. All six are identical (lot id, area, corners, zone, overlays, heritage, station, kerb flag, height), so the sheets are reproducible and do not depend on timing. Nothing in the sheets looks odd on a read-through:

| Site | Lot | Area m2 | Zone | Overlays | Station (m) | Official kerb | Tallest neighbour |
|---|---|---|---|---|---|---|---|
| hawthorn | 2\PS733527 | 759 | C1Z | BFO2, EAO, PO1 | Glenferrie (290) | no | none published |
| footscray | 1\TP128421 | 181 | ACZ1 | DCPO2, HO3, PO1 | Footscray (232) | yes | none published |
| preston | 23\LP7668 | 574 | HCTZ2 | DCPO1, HO186, ICO1 | Bell (321) | no | none published |
| chatswood | 1//DP724850 | 1617 | E2 | HOB 246.8 m(RL) | Chatswood (53) | no | none published |
| parramatta | 23//DP651527 | 633 | MU1 | HOB CA | Parramatta (291) | yes | none published |
| geelong | 1\TP821518 | 464 | ACZ1 | DDO36 | Geelong (591) | no | 11.5 m |

Still to do by eye (needs a browser that can reach the preview, e.g. the new PC): compare each row with the app on the same lot and then set `checked` in the sheet. Items worth a look: Hawthorn `BFO2` (an unusual code, check it is the Bushfire-type overlay code Vicmap really publishes), Preston and Footscray heritage codes, Chatswood and Parramatta overlays being height-of-building codes only.

<!-- table -->
| Site | Mode | Run | Date | Wrong facts | Position m | Height m | Reach | Calls | Minutes | Trace | Differing facts (consistency) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| peel-st | with | 1 | 2026-11-08 | 0 | – | – | 14/15 | 16 | 7 | 100% | – |
| peel-st | without | 1 | 2026-11-08 | 1 | – | – | 12/15 | 42 | 16 | 0% | – |
