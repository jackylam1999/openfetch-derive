# Vic aerial road surface (thread "Trace kerbs in the other 11 Vic suburbs", 19 Nov 2026)
Jacky 19 Nov 2026 01:39Z: "If tracing helps you can trace them too" (Vicmap aerial, base.maps.vic.gov.au AERIAL_WM_256, zoom 19, 0.25 m).
1. `mklab.py S boxes.json <box ...>`: per City of Melbourne box, aerial mosaic + road mask (council carriageway, channel, kerb, arterial,
   tram polygons) + valid mask (inside the City, minus 20 m round any Vicmap centreline the council drew no road under).
2. `kaggle_train.py`: Kaggle T4 notebook, ResNet-34 U-Net, kerb band (1.5 m) weighted 5x, 100 min; Carlton and North Melbourne held out.
3. `cellmos.py` aerial squares (1 km + 64 m) -> `kaggle_predict.py` road probability squares p_<x>_<y>.png -> `../aerroad.py` reads them.
4. Check: `evalw.py` (samples), `../study/truthcmp.py` (rings vs council kerbs). Held out: Carlton 82% / 93%, North Melbourne 82% / 95%
   within 1 m / 2 m (OSM-only: 73% / 87% on 3 blocks).
Run: `KERB_AER=<prob dir> python3 run_vic.py <prep> <out>`.
5. Version 19-c test (19 Nov 2026, CPU only, thread "Fix Vic gap kerbs, version 19-c"): three side rules in `../aerroad.py` tried against City of Melbourne kerbs
   (within 1 m, Carlton / North Melbourne; baseline with the rules off 83% / 87%): GAP (a side whose sorted offsets jump more than 1.2 m, both levels
   at least 15% of samples = angle-parking bays, left blank) 83% / 87%, on by default; STRIP (lot front to kerb strip looks like road, paved footpaths)
   82% / 86%, off; BAND (road probability past the kerb under 0.75, canopy) 82% / 84%, blanked 40% of rings, off. Env: KERB_AER_GAP, KERB_AER_STRIP, KERB_AER_BAND.
   The 91% North Melbourne figure of -b was not reproduced (same model, rebuilt inputs: 87%). Inputs kept in the project folder .notes/kerb-vic-aer/inputs/.
