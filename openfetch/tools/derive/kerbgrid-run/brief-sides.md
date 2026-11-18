# Side-by-side look (inner Sydney kerb rings)

Each image holds 2 tiles of NSW aerial, north up, 800 px each; the label top-left of each tile is the block id. The THICK MAGENTA
closed line is a drafted kerb line around ONE street block. Thin yellow/teal lines are other data; ignore them.
For each block, look at each side of the magenta ring in turn (north, east, south, west, plus any short corner sides) and
say what is directly beside the line on the outside: "road" (grey road pavement with a carriageway, parked cars or road
markings), or something else (roof, yard, lane under 5 m wide, path, park, water, car park, inside a courtyard).
Verdict OK only if every side has "road" next to it and the line does not cross any roof or close across a street mouth.
Otherwise ODD, naming the side and what is there. A narrow but real street with cars on it counts as road.
Read ALL your images in ONE turn (parallel Read calls), then write a JSON file mapping every block id you saw to
"OK: N road, E road, S road, W road" or "ODD: <side> <what>" to the path in your task. Reply with only the counts.
