# Draw kerbs for whole suburbs (thread "Draw kerbs for whole suburbs", started 7 Nov 2026)

Follows kerbs-more-real-kerbs.md (Jacky chose "Draw whole suburbs", 7 Nov 10:06Z).

## Done (cloud)
- kerbapply.py: `boxes / fetch / draw` take a NSW suburb name; boxes = every 1 km MGA56 square the suburb outline covers by
  more than 5 ha (outline cached as <out>/<NAME>.suburb.json). The old `AREA lon lat km` form still works.
- 20 shipped suburbs: 155 squares, 74 drawn on 4-5 Nov, 84 new (list busiest first: kerbs-whole-suburbs-boxes.json).
- LiDAR: 43 of the 84 new boxes sit in a 2 km ELVIS tile that already lies under an old box (held for sure). The other 41 need
  up to 24 tiles (lidar_tiles_maybe_missing); 13 of the 49 held tiles are not under any old box, so some may already be held.
  Check on the PC: `dir C:\kerb\lidar-ship` names vs the list. ELVIS orders need Jacky's direct OK in the thread.

## Next (PC, Remote Control)
1. Per suburb, busiest first: `kerbapply.py fetch C:\kerb\ship SUBURB`, then `dem` for boxes with LiDAR, then
   `draw C:\kerb\ship <pc-16-1 model> 0.8 SUBURB` with KERB_CFG side-street-eval.json. Boxes without LiDAR ship "partial".
2. Merge the new boxes' traced lines with the 2026-11-05 traced lines (kerbs-nsw.geojson.gz), drop shared-box duplicates.
3. Cloud: kerbregular.py run -> kerbnet.py (branch nz1mnq a0499a5 or later; owned by thread "Fix kerb corners for version d"
   since 7 Nov 10:13Z, do not edit) -> kerbreview.py (must pass) -> kerbs-check.py -> kerbcover.py per suburb.
4. Main: version folder + catalog + deployer "next combined preview" line only after the reviewer passes; no own deploy.
