# Is there a built road beside the magenta dots?

Each sheet holds up to 4 tiles of NSW aerial photo. In each tile the cyan line is a drawn kerb ring around a block of houses. The
magenta dots mark one side of that ring. The label at top left gives the tile number, the ring id and the tile width in metres.

For each tile answer one question: **beside the magenta dots, on the side away from the houses, is there a built road (grey or
black pavement a car can drive on, usually with cars, markings or kerbs)?**

- `ROAD`: a built road runs beside the magenta dots for most of their length (the dots may sit a few metres off the road edge; trees overhanging part of a road are fine if pavement shows through or continues on both sides).
- `NO ROAD`: beside most of the dots there is no pavement: grass, trees, bush, a park, backyards, a creek, a rail line, a footpath or walkway only, a car park inside a property, or an unbuilt strip between back fences. Example: dots running along a strip of trees and grass between rows of backyards, with no pavement in it.
- `PART`: pavement beside some of the dots but a clear stretch of 20 m or more with no road (say which end).
- `CANT TELL`: grey tile or too unclear.

Be strict: if you cannot see pavement beside the dots, it is not ROAD. Missing kerbs elsewhere do not matter, only this side.
