# Kerb seen-share test on version k (11 Nov 2026)

Question: can a per-block "seen share" pick out the kerb blocks of version k that are safe to ship? No new build, no new tidy rule.

## Method
- Tiles: the 96 judged 70 m tiles of the k review (56 reviewer sheet + 40 random places; verdicts in .notes/kerb-k/reviewer-independent/).
- Per tile (seenshare.py): seen share = part of the drawn kerb within 1.5 m of a raw traced kerb; both-sides = share of local-street
  sample points (every 5 m) with a kerb on each side within 15 m, for the drawn kerb and for the raw traced kerbs; main-road length in the tile.
- Swept every cut-off of those four numbers; counted WRONG and UNSURE tiles as not safe. Per-tile numbers: tile-features.json.

## Result: no cut-off gives zero wrong
Verdicts: 43 OK, 49 WRONG, 8 UNSURE (96 tiles; 29 WRONG + 4 UNSURE of 56, 16 + 4 of 40).
- Best cut-off (seen 100 %, both sides 100 %): 19 tiles pass, 3 of them not OK (A32 hump over parked cars, A56 lines on a 4-lane road, R22 wobble through angle parking) = 84 % clean, not 100 %.
- 7 WRONG tiles read seen 99-100 % with both sides present (A20, A32, A56, R3, R9, R11, R22, A49). The faults are drift of a traced line, wobble, and lines on main roads,
  which the traces themselves contain. Seen share measures coverage, not whether a traced line sits on the kerb. Looser cut-offs let in more wrong tiles.
- The other WRONG tiles are unseen stretches (seen 0-50 %): the share does catch those, so it works as a "blank" test but not as a "safe" test.
Conclusion: stop here. The 40 fresh places were not run (the first gate failed). Shelve OpenFetch kerbs; official council kerbs are the kerb layer.

## Official kerbs first in the app: confirmed from code and registry
Kerb lines is thing "kerbs". Parramatta (parrad.kerbs), Northern Beaches (nbc.kerb), Sutherland (ssc.kerb-and-gutter), Wollondilly (wsc.kerb-and-gutter) are
kind official, source official, area-only. core/search/things.js ranks official 2 > OpenFetch-made 0.5 > OpenStreetMap 0, so they show first in their council areas.
Not run in a browser.

## Next
More councils with official kerb lines, busiest first (tools/priority/TOP.md); the registry already lists Woollahra, Canterbury-Bankstown, Liverpool.
