# Kerb ring review (NSW, 19 Nov 2026)

Each sheet is 2x2 tiles of NSW aerial photo (north up). The label top-left of a tile is a block id and the tile width in metres.
THICK MAGENTA closed line = a drafted kerb line around ONE street block (the one being judged).
Yellow = kerb lines that already exist. Thin cyan = other drafted rings (ignore them, they get their own tile).

The owner's bar: a line a metre or two off the true kerb is fine if it is generally right. Only ODD lines fail.
Mark a ring ODD if ANY of these is true anywhere along it:
- a stretch runs over a roof, through a building, through back yards, or between houses instead of along a road;
- a side runs beside something that is not a built road with a carriageway: a rear lane or service lane, a footpath or park path,
  a rail line or tram line, a creek, bush or a tree strip, a construction site with no road yet, a car park inside a property;
- it closes straight across a street mouth, an intersection, a cul-de-sac or a car park entry (a kerb runs past a driveway or a
  narrow lane mouth, that is fine; it never runs across a street that carries traffic);
- it sits in the middle of a road, or on the far side of a road (beside the other block);
- it doubles a yellow line that is already there, or crosses a yellow line;
- you cannot tell because the photo is blurred, grey or covered.
Otherwise mark it OK.

Read ALL your sheets (several Read calls in one turn is fine), then write a JSON file mapping EVERY block id you saw to "OK" or
"ODD: <few words>" at the path in your task. Reply with only the counts (OK, ODD). Use no other tools and write no other files.
