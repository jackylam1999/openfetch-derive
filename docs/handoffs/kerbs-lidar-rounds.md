# Handover: kerb training with LiDAR (2 Nov 2026 ~06:50Z)
From thread "Train LiDAR kerb model on Jacky's PC". Read AGENTS.md (project files), docs/handoffs/kerbs-method.md (project files), then
`python3 openfetch/tools/derive/kerbloop.py brief kerb-learn/state.json`. PC setup details: project memory kerb-pc-training.

## Goal and standing rules (Jacky)
- Kerb lines good enough to ship (found >= 85%, offset <= 0.3 m, precise >= 70% on every held-out box), busiest areas first
  (tools/priority/TOP.md).
- LiDAR first; aerial kept only while it clearly helps (it does: round 11, below). Train on BOTH Kaggle and the PC when both are free.
- AUTONOMY (1 Nov 13:14Z): never wait for his decision during training; pick the most sensible next step, run it, tell him after.
- Hidden kerbs (1 Nov): estimate kerbs hidden by cars/trees "like a human would"; filled kerbs go in the SAME kerb layer.

## State
- Code + state: openfetch-derive branch claude/project-thread-ayjhtw (latest a427aea). kerblearn.py, kerbloop.py
  (MAX_ROUNDS 30, CONTROL has more=1), kerb-learn/state.json (best = pc-12-1, 0.804, cfg more=1, status running), LOG.md, queue.json.
- PC: Jacky's laptop, RTX 3070, everything in C:\kerb. Driver kerb-learn/pc/pc.py: `data`, `round [side.json]`, `record <tag>`.
  ~110-127 steps/min (Kaggle 21); each run = ~45 min tile loading + training + scoring; a 150-min variant ~55 min total.
  Start rounds DETACHED (Start-Process) so they outlive Remote Control. RC watchers die when the session restarts: always
  schedule a fallback check (send_later) instead of trusting the watcher. Keep laptop plugged in, lid open.
- PC permission check: installs/credentials need Jacky's own words in the thread. RC may commit/push only state.json + LOG.md.
- Kaggle: weekly GPU quota used up; resets Sat 7 Nov 00:00 UTC. Driver kerb-learn/kaggle/kaggle.py (KAGGLE_KEY env).
- Windows fixes in kerblearn.py: spawn pool capped at 4 workers (_pool), scikit-image in requirements.

## Results (F1 on the 8 NSW LiDAR check/held-out boxes; noise ±0.006)
- Round 10: control 0.772, LiDAR + aerial 0.776, LiDAR only 0.780.
- PC side runs: LiDAR only 300 min 0.782 (no gain); two-judge label cleaning 0.758 (dropped).
- Round 11 (Kaggle): LiDAR + aerial, photo hidden on half the chips (pdrop 0.5) 0.798 -> aerial KEPT, this is the base.
- Round 12 (PC): control 0.797, pdrop 0.75 0.796, apartment boxes (more=1) 0.801 (apartments 0.675 -> 0.716).
- Round 13 (PC): control 0.802, more + pw6 0.804 (apartments 0.723) = BEST (pc-12-1 model), pw6 0.798.
- Round 14 (PC): control 0.797 (ran without more=1), hide 3 patches per chip (occlude 3) 0.801, occlude 6 0.800.
  => plateau around 0.80. Model tweaks have stopped paying; next gains must come from filling hidden kerbs.

## RUNNING: round 15 on the PC (started ~06:45Z 2 Nov)
Control vs "apartment boxes + hide 3 patches per chip, 300 min" (occlude 3, minutes 300), starting from the pc-12-1 model
(copied to C:\kerb\data\best\model.pt; previous best saved as C:\kerb\saved\best-pc-13-0.pt). RC was told to run
`pc.py record 15`/the round tag, commit + push state.json + LOG.md, report, and NOT start another round (queue empty).
Check: RC on the PC, look in C:\kerb\out\<round>\*\result.json "lidar" block; if not recorded, record it yourself.
Expected done ~09:00Z. If it wins by > 0.006 promote it; either way, the next work is the fill step below.

## NEXT: lot-frontage fill (no GPU needed; build in kerblearn.py as a post-process, CFG "gapfill")
Idea (what a human does): where a street has kerb on some stretches but not others, the missing stretch sits parallel to the
property line at the same verge width.
1. For each road segment, take the model's kerb lines and the lot boundaries facing that road (lots geojson already fetched per box;
   lot_side() tells which side the lots are on; reference() already offsets lines toward lots by a measured distance).
2. Measure the verge width = median distance from visible kerb to the lot frontage along the same street (and same side).
3. Where a frontage has no kerb within ~verge + 1 m, draw the frontage offset by that width toward the road; clip at
   intersections/driveway-free gaps; only fill gaps up to ~40 m (longer = probably no kerb), and only where the street has
   enough visible kerb to measure from.
4. Output into the same kerb layer. Score with/without on the same boxes (found / precise / offset); keep it if found rises
   without precise dropping more than the noise. Queue item "fill hidden kerb gaps along the road" (gapfill) in queue.json.
5. Then, if still short of 85%: gap-repair model (learn to join broken lines; Batra et al. CVPR 2019 "orientation + connectivity").

## Open items with Jacky
- Melbourne LiDAR: none open (ELVIS empty over central Melbourne; Greater Melbourne 2017-18 and DTV 2021-24 are licensed via
  DTP Coordinated Imagery Program, quote only). Offered to DRAFT emails to DTP (quote + free non-commercial access, ~4 x 4.5 km
  inner Melbourne) and Merri-bek (virtual@merri-bek.vic.gov.au, own 2021 LiDAR). No answer yet. Drafts only, never send.
- Newer NSW LiDAR (post-2020) email offer: no answer yet.
- Aerial fallback for streets built after the LiDAR survey: told Jacky, not built.
- Round 11 result pictures: /mnt/project-files/kerbs/results-2026-11-01/.
