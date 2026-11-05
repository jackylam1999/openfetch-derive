# NSW kerb shipping run on the PC (thread "Ship NSW kerbs on local streets", started 4 Nov 2026)

Plan: kerbs-direction.md "4 Nov 09:40Z" items 2-3 and "4 Nov 11:40Z" checks A-C (both approved by Jacky).

## State at 4 Nov ~12:00Z
- Arterial round (item 3): kerb-learn/pc/side-arterial.json, 6 train_new boxes in boxes.json (deewhy, frenchsforest, belmore,
  lakemba, rosebay, rydalmere; Lakemba replaces Bass Hill: the NSW imagery server refuses 0.1 m photos at Hume Hwy Bass Hill at
  every tile size). Variant a = boxes only, b = boxes + CFG rare 0.3 (kerblearn.rare_pool). The new boxes have NO LiDAR grid.
  Running: C:\kerb\arterial.ps1, log C:\kerb\round.log + C:\kerb\out\side-arterial\<id>\run.log. Started ~11:00Z, about 5.5 h.
  Keep rule: main-road found +10 pts over the 8 boxes with scenario >= 0.814, or scenario >= 0.823. Under +5 pts: stop ALL training.
  pc.py round overwrites C:\kerb\kp\*_derived_*: rerun C:\kerb\streeteval.ps1 afterwards (memory: kerb-training-no-waiting).
- Ship run (item 2): openfetch/tools/derive/kerbapply.py. 20 suburbs (centres geocoded by hand, list in C:\kerb\ship-boxes.json),
  2 x 2 km each on the MGA56 km grid = 72 unique 1 km boxes in C:\kerb\ship (all fetched). LiDAR: 49 newest-survey tiles (ELVIS
  orders 2652614 + 2652617) in C:\kerb\lidar-ship; grids via C:\kerb\shipdem.ps1 (log C:\kerb\shipdem.out).
  Draw (GPU, after training): per suburb `kerbapply.py draw C:\kerb\ship <model> 0.8 <suburb> lon lat 2` with KERB_CFG from
  side-street-eval.json; shared boxes are drawn once (<box>_drawn.json marker).
- Checks: kerbsanity.py (B; calibrated on the 8 scored boxes: STEP tracks local found best, BOTH-SIDES is noisier; worst scored
  box both 20% (olympicpark), step 29% (wocheck)), kerbspot.py (C; 60 patches, 5 sheets). Step A (Parramatta end to end vs council
  lines) still to write: compare the ship boxes' lines with the parramatta hold box's council kerbs (compare_kerbs.py, 1 m).
- Output: G:\My Drive\OpenFetch (Claude)\derived-layers\kerbs\<version>\ (one GeoJSON, WGS84, properties road / source / length_m)
  + README; the cloud thread "Publish NSW kerb layer from PC files" does manifest, tiles, registry and the deployer line.
- ELVIS: future orders go to jackylamcloud@gmail.com (its own Claude in Chrome browser on the PC).
