# Handover: kerb training, LiDAR rounds (1 Nov 2026 ~03:00Z)
From thread "Continue kerb training rounds 5 to 8" (ran out of follow-up rounds). Read AGENTS.md, docs/handoffs/kerbs-method.md,
then `python3 openfetch/tools/derive/kerbloop.py brief kerb-learn/state.json`.

## State
- Code + state: openfetch-derive branch claude/project-thread-84nnno (PR #4). Kaggle driver kerb-learn/kaggle/kaggle.py
  (round / status / record / data / lidar). KAGGLE_KEY env var; plain `kaggle` CLI needs `export KAGGLE_API_TOKEN="$KAGGLE_KEY"`.
- Best model 0.761 scenario score (Satlas Swin-v2-B encoder, kept round 6 log numbering 7; first gain since round 1).
  Not kept (all within the 0.006 noise bar): learn from all misses 0.745, clDice 0.747, photo-edge label check 0.747,
  4 new apartment/dense boxes 0.763 vs 0.761 (apartments +0.03, dense -0.01). Several aerial years: skipped (Jacky).
- RUNNING (pushed ~22:41Z 31 Oct, kernel v9): control vs "Satlas: train 300 min more" vs "Satlas: bigger view (384 px)".
  Next step: `kaggle.py status train`, then `kaggle.py record`, commit state.json + LOG.md.
- GPU quota: ~30 h/week, ~19 h used by 31 Oct night; resets Sat 00:00 UTC.

## LiDAR (Jacky 1 Nov 02:53Z: "lidar is a must ... lidar or mix of lidar and aerial, let's try it")
- ELVIS NSW orders (9 zips, links in kerb-learn/lidar_links.json, expire ~2 Nov) were turned into 0.25 m ground grids by Kaggle
  notebook openfetch-kerb-lidar (kerb-learn/kaggle/lidar_kernel.py): {box}_dem.npy for bankstown, cb1, cb2, yagoona, nparramatta,
  rydalmere, wentworthpt, melrose, carlingford, epping, wo1, wo3, plus partial parramatta, olympicpark, paddington. Ground density
  only 1-6 points/m2 (2019 surveys ~1.5-2, 2020 ~4.5-5.5); steps() smooths gaps (sigma 1.5 cells).
- Queued (kerb-learn/queue.json, ready): "two-judge label cleaning": training pieces need photo edge AND a >=7.5 cm ground step
  (boxes without LiDAR: photo judge only). Scoring reference unchanged (check/held-out boxes lack LiDAR).
- To do for Jacky's ask (LiDAR alone, LiDAR + aerial, vs aerial-only control, one change per round, per-scenario scores):
  1. Order LiDAR for every other NSW box (pw1-8, nb9-10, cb3-8, roselands, milperra, villawood, wo2, nbcheck, cbcheck, wocheck,
     olympicpark, monavale, newport, parramatta, paddington): Remote Control on Jacky's PC, ELVIS email orders to his Gmail
     (bucket is Requester Pays, no direct download), newest survey, skip 2013 1.56 pts/m2 surveys. He pastes links; rerun
     `kaggle.py lidar <commit>` after adding links. Vic LiDAR is CC BY-NC: Vic boxes stay aerial-only.
  2. Code: LiDAR input channels (ground height minus 3 m local median, and gradient magnitude, resampled to 0.1 m, plus a
     has-LiDAR mask; zero where none) via context(); variant A "LiDAR + aerial" (extra channels), variant B "LiDAR only"
     (RGB zeroed). Score on NSW boxes that have LiDAR; report per scenario next to the control.
- Also queued (todo, needs code): "fill hidden kerb gaps along the road" (Jacky's centreline idea, post-processing).
