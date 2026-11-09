# Benchmark prompt (fixed; do not edit between runs)

Same job as the 211 Peel St trial (8 Nov 2026), with the address swapped. Paste it word for word into a fresh session, with `{address}` replaced by the site's address from `sites/<site>.json` (`lot.address[0]`, or the lot id for NSW sites).

> I'm an architect starting a feasibility study for {address}. Please do a site analysis I can draw from, using official government and council data wherever it exists:
> 1. the lot (lot and plan number, area, boundary), and the address;
> 2. the buildings on and around the site, with heights, and say where each height comes from;
> 3. the planning zone and every overlay on the lot, and any heritage listing or grading;
> 4. ground levels (AHD) across the site and the fall;
> 5. kerbs, footpaths and street trees along the frontage;
> 6. the nearest train station and the tram or bus stops nearby, with distances;
> 7. a winter solstice (21 June) shadow study, 9 am, 12 noon and 3 pm, from the neighbouring buildings onto the site;
> 8. a list of every source used, with its year and licence.
> Give coordinates in GDA2020 MGA and levels in AHD.

Two modes, same words:
- **with**: the OpenFetch connector is connected; open web also allowed.
- **without**: no OpenFetch connector, no OpenFetch website; open web only.

Each run is a fresh session (no memory of earlier runs). Three runs per site and mode, for the consistency score.
