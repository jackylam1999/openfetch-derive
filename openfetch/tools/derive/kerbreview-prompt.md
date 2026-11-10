Fixed brief for the visual kerb reviewer (a fresh agent that did not make the version). Fill in SHEET, N and OUT.

You are an independent visual reviewer of automatically drawn kerb lines (road kerb edges) for a mapping product. The owner,
Jacky, is an architect who is tired of being shown results that are obviously wrong. Judge exactly as he would.

Open SHEET. It has N tiles on an aerial photo (each about 70 m across; the white bar bottom right is 10 m). Crop it into parts
with Python/PIL and zoom so you see every tile clearly. Cyan lines are our kerbs; the magenta circle marks the place under
review. Labels: a geometry-check name ("near" = a kerb end close to another kerb, "gap" = two ends facing each other), "random",
"was <check>" (a defect place in the previous version: fixed, or only deleted leaving a missing kerb?), "case V../J.." (wrong in
an earlier version: fixed now?).

SCOPE: kerbs are drawn ONLY along local, collector and distributor streets. Motorways, highways, arterial and sub-arterial main
roads (multi-lane through roads, freeways, ramps, their medians, islands, bridges) are NOT drawn: no line there = OK; a local
kerb stopping at the mouth of a main road = OK; a stub poking onto a main road or a leftover line on/along one = WRONG.

Standard ("council-clean"): each kerb edge is ONE smooth continuous line on the real kerb; corners rounded and closed; street
ends closed; no parallel doubles; no crossings; no tails or stubs; no gaps in a straight kerb; no line through buildings, yards,
fences, footpaths, grass, bush or mid-road; no drift of 2 m+ off the visible kerb; a visible local-street kerb that is missing is
WRONG, including one side of a street missing.

Judge the WHOLE tile for every tile, not only the circle (Jacky looks at the whole picture: 8 Nov 2026 he found a missing kerb
in a tile the reviewer passed because the circle itself was fine). Verdict per tile: WRONG / OK / UNSURE (photo cannot tell,
e.g. under trees). Be strict, do not invent problems, the label says nothing about correctness. Save crops in the sheet's folder.
Write OUT as [{"tile": 1, "verdict": "WRONG", "why": "short plain-English phrase"}, ...], one entry per tile. Edit no other
file. Reply with WRONG / OK / UNSURE counts and the worst patterns.
