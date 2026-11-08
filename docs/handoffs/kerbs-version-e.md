# Kerbs version e (7 Nov 2026), handoff for version f

Thread "Guide kerbs with property boundaries" (lead kerb builder after the coordinator handed over all kerb agents).

## What e is
- Code: openfetch-derive branch claude/project-thread-c09cop 8871364 = corner-fix work (12v8yq 5bb72b7) + reviewer tool (v6yk7j)
  + `no_motorway()` (fh 1 stretches out, 11 km) + `--local-only` (Jacky 7 Nov 14:04Z go: kerbs only along fh 5-7 streets;
  209 km on fh 1-4 taken out, then tidy + unhook on the cut ends).
- Run: `kerbnet.py nsw-r11.json lots roads out.json --traced-only-area --local-only` (~11 min, 4 cores) on
  derived-layers/kerbs/kerbnet-inputs-2026-11-07.tgz; output + review in /mnt/project-files/.notes/kerb-e2/ (not in derived-layers,
  so the manifest stays clean until a version passes).
- Note: the published e file was tidied once more after the run (tidy + unhook after the scope cut); the code now does this itself.
- Geometry: all zero except fold 2 (cap now 0). Parramatta box 65.6 found / 84.2 precise (box includes main roads, now out of scope).
- Visual: FAIL 12 of 37 wrong (d: 19 of 28); 15 of 19 old cases fixed or out of scope. Verdicts .notes/kerb-e2/reviewer/.

## Fix list for f (EPSG 7856, all now permanent cases, v6yk7j a857120)
- + crossings through junctions (the 2 fold spots): 337442 6247053, 334885 6250056
- corner runs on into a line through footpath/park: 332370 6247179
- corner bulges over footpath: 329360 6246334; diagonal kink into junction: 325880 6249700
- hook into a gap between buildings: 328291 6246090
- wavy line through angle parking: 314080 6254243; 3 m drift onto verge: 325244 6255923
- NE corner kerbs missing: 337938 6247094
- V31 322686 6254752 one median side + car-park stub; V41 333980 6251790 motorway-edge leftover (scope cut uses nearest
  centreline; a ramp/service road nearer keeps it: cut by distance to any fh 1-4 carriageway instead)
- borderline: cul-de-sac end open east of 314096 6254182; stubs beside main road near tile 36
- merge (Y) spots: 5 of 10 checked were wrong; e has 15

## Do not retry
- Lot / property boundary guide (`--lot-guide`, off): Parramatta 69.7/82.8 -> 68.1/82.1, open ends +47 %; residential split
  (Parramatta, Mona Vale, Newport) loses 1-6 found for <= +3 precise. Council residential kerbs sit within 1 m of their side's
  median verge 86-91 %, but verge measured from our traced kerbs is not good enough; cadastre up to 5 m off the aerial at
  333028 6244986. Easements lie inside lots. Pictures .notes/kerb-lot-guide-test/.

## Next
- Fresh thread builds f from this list; whole-suburb inputs arrive from thread "Draw kerbs for whole suburbs"
  (derived-layers/kerbs/kerbnet-inputs-2026-11-07-whole.tgz, merge + kerbregular + lots/roads for 84 new boxes).
- Then `kerbreview.py check out dir --prev .notes/kerb-e2/reviewer/review.json` (cases from v6yk7j latest), message the
  reviewer thread at pending visual; post the sheet to Jacky either way (he asked to see local kerb reviews).
