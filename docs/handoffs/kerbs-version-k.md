# Kerbs version k: closed loop per street block (8-9 Nov 2026) - PAUSED

Thread "Build kerb version k from block loops". Jacky picked the kerb reviewer's option 1 ("skeleton first"). Paused 9 Nov 03:11Z
(Jacky: stop automatic work until the Wednesday token reset). Code: derive branch claude/project-thread-pjr3xa (on j 2233c96).
Files: /mnt/project-files/.notes/kerb-k/ (full-k4.json.gz = run 4, post6.json.gz = run 4 + tidy pass, scripts/, ref-parra-gda2020.json).

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

## Where it stands (resume here)
- Run 4 (+ tidy pass applied afterwards, post6): 3,047 km, geometry fold 5, gap 1, near 66 (under cap), no other kind; one
  old case back (V104, near at 336336 6243644, made by the besides cut). The 5 folds were thin closed rings on loops where
  nothing was traced (fuse returned early before the opening): fixed in code (unseen loops now go through the opening).
- Run 5 (all of the above built in) was started and STOPPED for the pause. Next step: run it (command above), run the review,
  look at V104 and anything left, then send the geojson path + Parramatta precise to the reviewer thread "Automate kerb quality
  review" for the visual sheet and the 40-place headline (j baseline 52.6 % clean; k must beat it).
- Known weak spots: main-road junction cut ends; streets whose centreline sits on the kerb (Parramatta 315900 6256385);
  streets lying in road-parcel lots are still dropped as lanes (a road-parcel rule was tried: +2 km at 19 % precise, removed).
