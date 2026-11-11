# Kerbs version k: closed loop per street block (8-10 Nov 2026)

Thread "Build kerb version k from block loops". Jacky picked the kerb reviewer's option 1 ("skeleton first"). Paused 9 Nov 03:11Z
(token reset), resumed 10 Nov 11:20Z (Jacky: "keep the kerb running"). Code: derive branch claude/project-thread-pjr3xa (on j 2233c96).
Files: /mnt/project-files/.notes/kerb-k/ (kerbs-nsw-k.geojson.gz = run 7, reviewer/ = its review.json + sheet, scripts/,
ref-parra-gda2020.json).

## How to run
`kerbnet.py nsw-r11.json lots roads out.json --traced-only-area --skeleton --local-only --fuse-with nsw-traced-raw.json`
on derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz (~30 min, 1 core; pip install numpy shapely scipy pyproj).
A 1 km box (`--box 315000 6256000 316000 6257000`, Parramatta council box) takes ~1.5 min.
Review: kerbreview.py from derive v6yk7j db4f11f or later (loop seams no longer count as free ends), with `--roads roads
--prev /mnt/project-files/.notes/kerb-j/reviewer-independent/review.json`.

## Scoring Parramatta
ref-parra.json in the inputs is GDA94 (EPSG 28356). Move it to GDA2020 (7856) before scoring, else every version reads ~40 %.
The moved copy is .notes/kerb-k/ref-parra-gda2020.json; scripts/score.py (precise/found, 1 m) and scoped.py (found on local
streets only) in .notes/kerb-k/scripts. Box 315000 6256000 316000 6257000.

| | precise (1 m) | local found |
|---|---|---|
| version j | 80.6 % | 65.0 % |
| raw traced lines | 86.6 % | - |
| k loops, fused on regularised traces (7 Nov method) | 81.4 % | - |
| k (run 4 code) | 85.0 % | 66.8 % |

## What skeleton() does (kerbnet.py)
1. build() with CLOSE_EDGE: street network closed on the area edge (blocks beside a railway/creek/data edge still get a face);
   narrow streets (<7 m between lots) kept when kerbs are seen both sides (kerbed_both); dead-end caps: street shortened
   (cap_back) so the round cap stays out of house lots; block arms thinner than 3 m opened away (OPEN_R).
2. fuse() onto the RAW traced kerbs (--fuse-with; 4.5 m reach, 2-sample window), never across a street centreline (FUSE_WALL),
   corners (over 35 deg in 6 m) not moved, fused loop opened again and untied; a loop that is mostly thin arms is dropped.
3. Traced pieces on no loop dropped. far_cut: stretches >18 m from every street, within 2 m of the area-edge line, or >12 m
   from a street and running across it go. no_motorway (fh 1) and the local-only cut (fh 1-4). undup (doubles, 2.7 m).
4. kerbg.roundabouts (j's islands), then tidy: kerbg.guard x2, gapjoin, endpairs, snap_near, kerbg.besides, guard.

## Where it stands (10 Nov 2026)
Run 7 (full, ~31 min): 3,055 km; kerbreview (v6yk7j db4f11f, --roads, --prev j independent): every hard kind 0, near 50
(under cap), no old case hit -> **pending visual**; Parramatta precise 85.4 % (j 80.6 %, bar 82 %), local found 66.8 %
(j 65.0 %). Sent to the reviewer thread "Automate kerb quality review" for the sheet and the 40-place headline (j 52.6 % clean).
Final steps added since run 4 (skeleton() end): near_trim (free end 0.05-5 m from a kerb cut back until 5 m clear; fixed case
V104), short_cross (short bow-ties dropped; ends crossing another line within 12 m of the tip cut at the crossing), ring_pinch
(a closed loop folding within 2.5 m of itself gets a 2 m closing; a 2 m closing inside fuse for every loop lost 0.8 km in the
Parramatta box, so it is applied only to pinched rings). Fast check of a tidy step: scripts/post.py runs kerbnet steps on a
finished output in ~1 min instead of a 30-min full run.
Known weak spots: main-road junction cut ends; streets whose centreline sits on the kerb (Parramatta 315900 6256385);
streets lying in road-parcel lots are still dropped as lanes (a road-parcel rule was tried: +2 km at 19 % precise, removed).

## Reviewer verdict on k (10 Nov 14:21Z): FAIL, level with j
Visual 29/56 WRONG + 4 unsure (j 27/55); 40-place headline 55.6 % clean, 20/36 judged (j 52.6 %, 20/38, the same 20 OK
places). Geometry all 0, near 50. Files .notes/kerb-k/reviewer-independent/; new cases derive v6yk7j d083c5a.
Patterns: (1) missing kerbs: one street side gone (1/4, 27, 43, 52), old defect places now empty (22-24), side streets left
undrawn with the main kerb straight across their mouths (33, 40, 49; headline 4, 28, 35: the 7 m lane filter and road-parcel
lots), whole local streets (headline 20, 31), a corner (32), grass median both sides (37); (2) loops on the wrong ground: roofs
(11, 12, 54), across the road (6), in the traffic lane (50), on verges ~6 m out (15, 20, 29, 43, headline 21: unseen loop parts at
the default/frontage offset), grass with no road (39); (3) lines on main roads (10, 44, 48, 56; headline 22, 40); (4) open ends
mid-road (25, 44), ends 8-9 m short (11, 51), roundabout ring 2 m off its island (34). Still wrong: V16, V38, V39, V77, V78.
Loop rule (kerb-auto-loop): i, j, k in a row did not lower the wrong count, so the loop stopped and reported to the coordinator.
Precise rose (85.4 %) but what the eye sees did not: most wrong places are missing streets and unseen stretches, which
alignment does not measure. If continued, the lever is coverage of side streets (lane test) and where nothing was traced (blank,
not a guess: reviewer option 2), not more tidy rules.

## Decision (11 Nov 2026, quick Fable review asked by Jacky): stop the version loop, official kerbs first
Thread "Decide next kerb direction". Read: this file + kerb-reviewer.md only; nothing built or re-measured.
- **Option 1 (keep improving k): stopped.** i, j, k sit at 27-29 wrong of ~55 and the same 20 of ~38 random places clean.
  k raised alignment (85.4 %) but the eye result did not move: the faults are missing streets and stretches drawn where nothing
  was seen, which more tidy rules cannot fix. No version l.
- **Option 3 (official council kerbs first): this is the map.** It is already Jacky's rule (official, then OpenFetch, then
  OSM) and the only choice that meets zero mistakes today. OpenFetch kerbs stay on hold (off preview and live).
- **Option 2 (ship only passing blocks): not shippable as written.** The automatic checks all read 0 on k while half the
  viewed tiles are wrong, so "passes review" cannot yet be decided per block by a machine. It needs a per-block proof first.
- **Next step (one short thread, cheaper model, no new build):** on the finished k output, give every street block a "seen
  share" (part of its loop fused onto a traced kerb, both sides of each street present, no side-street mouth closed) and test
  it against the 92 verdicts already in .notes/kerb-k/reviewer-independent/. Go only if a threshold keeps zero WRONG tiles at a
  useful coverage, then confirm on 40 fresh random places with 0 wrong. If not, shelve OpenFetch kerbs and spend the effort on
  finding more councils with official kerbs (tools/priority/TOP.md, busiest first).
- Not checked here: that the four councils with official kerbs (Parramatta, Northern Beaches, Sutherland, Wollondilly) are
  all served first in the app's Kerb layer.
