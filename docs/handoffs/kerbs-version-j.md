# Kerbs version j (8 Nov 2026)

Thread "Build kerb version j". Code: openfetch-derive branch claude/project-thread-20snth (on nq5zda e62dd82, version i).
Files: /mnt/project-files/.notes/kerb-j/ (kerbs-nsw-j.geojson.gz, reviewer/review.json + review-sheet.jpg, STATUS.txt).

## How to run
Same as i. Full run with `--dump-g g.pkl` (~30 min), then `--from-g g.pkl` reruns kerbg.clean only (~13 min). Version j was made
with `--from-g` on a fresh i dump (the network before kerbg is unchanged from i). Inputs: derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz.
Needs only numpy, shapely, scipy, pyproj (pip install those four; the full requirements.txt is slow).

## What changed from i (tools/derive/kerbg.py only)
- Main roads measured, not one width per class: every main centreline (fh 1-4, not in a tunnel or on a bridge) gets its property
  line measured every 4 m each side from the lots (smoothed +-16 m, mouths left out). A kerb point more than MAIN_KEEP (5 m) inside
  that line and within MAIN_OWN (10 m) of its own street's distance is on the carriageway: main_tails cuts it, walks stop there.
  Fixes i V41 (motorway edge), V43 (slip loop), V65 (across junction), V78 (past stop line). main_tail_m 396 -> ~22 km.
- roundabouts(): small round face of local centrelines with no lot in it (spokes merged) -> island circle one lane (4.3 m) in,
  radius 3.5-8 m, only where nothing is drawn. ~300 islands (V33).
- in_lots(): a stretch 4 m+ lying 2 m+ inside a property lot (lots holding a centreline are road parcels, skipped) goes; run
  before sides/extend so the street is redrawn (roof stubs, forecourts, yards: V42, i tile 1).
- sides(): offsets tried in order, first one 2.2-12 m wins: own side's, the other side's mirrored about the RESERVE (this side's
  property line less the other side's verge; centrelines are often off the middle, i tile 2), the other side's, property line
  less the class verge, then the class's usual kerb offset (KO). A street with nothing either side is drawn when both its ends
  meet drawn kerbs (V32). +35 km.
- pair_join(): two free ends facing each other up to 20 m apart become one kerb (driveway breaks, V97); also across an unkerbed
  street's or lane's mouth up to 10 m (layback, V96); a long kerb round a block left open is shut into its ring; two ends side by
  side 2.7-6 m apart with no street between get a round nose (median noses). Stubs under 15 m with both ends free near a kerb go.
- off_centre_ends(): a free end lying within 1.5 m of a centreline is taken back (V98).
- near_ends: a T across a centreline is allowed when the gap is under 3 m (no street fits).
- guard(): last pass, the reviewer's inside (short line 75 % within 2.7 m of others) and fold (<2.55 m) rules once more.

## Result (kerbreview --roads, --prev i)
All kinds 0, near 120 (0.039/km; i 125), no case hit; 3,045 km. Visual: sent to the reviewer thread.

## Left for k
- Still missing sides on some streets (i V101, V92 south side, V32 west arm): sides draws them but later steps take them back;
  use KERBG_WATCH on the run's ends. /tmp debug helpers were: dump the input of sides() and rerun it alone in a few minutes.
- Roof stub V100 (306379 6188602) and the depot forecourt V94: the lot holds a centreline, so in_lots skips it.
- Unformed roads (V38): a centreline over grass still gets kerbs.
