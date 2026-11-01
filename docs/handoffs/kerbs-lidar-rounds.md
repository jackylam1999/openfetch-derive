# Handover: kerb training with LiDAR (1 Nov 2026 ~09:30Z)
From thread "Train kerb model with LiDAR". Read AGENTS.md (project files), docs/handoffs/kerbs-method.md (project files), then
`python3 openfetch/tools/derive/kerbloop.py brief kerb-learn/state.json`.

## Goal (Jacky)
Kerb lines good enough to ship (found >= 85%, offset <= 0.3 m, precise >= 70% on every held-out box), busiest areas first
(tools/priority/TOP.md). Jacky 1 Nov: "lidar is a must"; 09:19Z: **if aerial gives no clear advantage, move to LiDAR only and keep
training on it.**

## State
- Code + state: openfetch-derive branch claude/project-thread-icjanz (PR #5). Kaggle driver kerb-learn/kaggle/kaggle.py
  (round / status / record / data / lidar); `pip install kaggle`; KAGGLE_KEY env var (kaggle.py maps it to KAGGLE_API_TOKEN).
- LiDAR: all 40 NSW boxes (train, check, held-out) have 0.25 m ground grids ({box}_dem.npy) in the output of Kaggle notebook
  openfetch-kerb-lidar (17 ELVIS zips, kerb-learn/lidar_links.json; links expire ~2-3 Nov, the grids are kept by Kaggle).
  Surveys Sydney202005/202006 and Sydney/Penrith201906 (ELVIS "newest per tile"). NSW CC BY 4.0, credit Spatial Services.
  Vic boxes have none yet: Jacky 1 Nov OK'd Vic LiDAR (CC BY-NC) while the site is free; order Vic ELVIS for the com boxes
  (southbank, carlton, docklands, northmelb, melbcbd, kensington, southwharf, westmelb) and confirm top-30 Vic suburbs are covered.
- Ordering ELVIS: Remote Control on Jacky's PC (folder G:\My Drive\OpenFetch (Claude)); the Order click is refused by the PC's
  permission check until Jacky writes in the thread in his own words to place the orders ("Place it urself" worked). Links go to
  his Gmail; he pastes them. Then add to lidar_links.json, commit, `kaggle.py lidar <commit>` (processes all links again).
- Code (kerblearn.py): CFG lidar=1 adds 3 input layers (ground minus 3 m median, slope, has-LiDAR; lidar()); lidar=2 = LiDAR only
  (photo blanked, trains/scores LiDAR boxes only); pdrop = share of LiDAR chips with the photo blanked. result.json has a "lidar"
  block = score on LiDAR boxes with its own threshold; kerbloop.py judges LiDAR variants on it and NEVER promotes lidar=2
  (change that rule in record() if the switch to LiDAR only is made).

## FIRST NEXT STEP (Jacky 1 Nov 09:27Z: "Yea you can use my pc but I don't know what to set up")
Train on Jacky's PC while Kaggle resets. Jacky does nothing: start Remote Control on G:\My Drive\OpenFetch (Claude), run
`nvidia-smi` (NVIDIA, >= 8 GB?), then install everything yourself (Python, CUDA PyTorch, the kerblearn.py requirements),
copy the data caches (Kaggle outputs openfetch-kerb-data*, -lidar, dataset openfetch-kerb-best) to a local folder off Google
Drive, and run the next round there with the same steps-per-minute (21). No suitable GPU: tell Jacky, offer Colab Pro.

## Results
- Round 9: Satlas train 300 min more 0.759, bigger view 0.757, control 0.759: photo model plateaued.
- Round 10 (LiDAR, on 8 LiDAR check/held-out boxes, F1): control 0.772, LiDAR + aerial 0.776, LiDAR only 0.780.
  LiDAR only: Parramatta CBD 0.71 -> 0.79 (precise 74 -> 85%), terraces 0.81 -> 0.84, wocheck 0.76 -> 0.81, Newport 0.76 -> 0.79;
  weaker: apartments/Olympic Park 0.67 -> 0.62, nbcheck 0.74 -> 0.68, flat grid 0.91 -> 0.90; offsets ~equal (0.26-0.40 m).
  LiDAR + aerial barely moved: new layers start at zero, the photo already explains the labels, model ignored LiDAR.
- RUNNING round 11 (pushed ~09:15Z, kernel v11): control vs "LiDAR + aerial, photo blanked on half the chips" vs same at 300 min.
  Check: `kaggle.py status train`; when COMPLETE: `kaggle.py record`, commit state.json + LOG.md, per-box numbers from
  /tmp/kerb-kaggle/out/*/result.json "lidar" block. A scheduled check fires ~14:15Z in the old thread.

## Decide next (Jacky's rule)
- If round 11's LiDAR + aerial does not beat round 10's LiDAR only (0.780) by more than the noise (0.006): make LiDAR only the main
  model (allow lidar=2 as best in kerbloop record, base cfg lidar=2) and keep training it; first target the apartments weak spot
  (Olympic Park: more apartment boxes with LiDAR, busiest first: Wentworth Point, Melrose Park, Rydalmere already have it).
- Aerial fallback for streets built after the LiDAR survey (2019-2020; busiest areas Waterloo, Zetland, Parramatta change fastest):
  draw from the aerial model where photo (2022+) and LiDAR disagree or LiDAR is older than the street. Told Jacky; not built.
- Top NSW suburbs (Sydney, Waterloo, Zetland, Erskineville, Alexandria, Parramatta, Randwick, Marrickville, Haymarket, Chatswood)
  sit in the 2019-2020 Sydney surveys (not individually checked on ELVIS).

## Open questions for Jacky
- Newer NSW LiDAR: none on ELVIS after 2020 for these areas; Spatial Services flies a CityMapper-2 since 2024. Offered to draft an
  email asking for post-2020 Sydney/Parramatta captures and ELVIS dates; awaiting his yes.
- (answered: use Jacky's PC, see first next step) GPU while Kaggle resets (30 h/week, resets Sat 00:00 UTC; nearly used up after rounds 9-11): offered (1) Jacky's PC GPU via
  Remote Control if NVIDIA >= 8 GB (check `nvidia-smi` first), (2) Colab Pro ~A$15/month, (3) GitHub free CPU (1-2 days a round).
  Awaiting his pick.
- Queued after the LiDAR rounds: two-judge label cleaning (kerb-learn/queue.json); "fill hidden kerb gaps along the road" (todo).
