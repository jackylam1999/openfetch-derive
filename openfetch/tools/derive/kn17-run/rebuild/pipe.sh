#!/bin/bash
# usage: pipe.sh <inputs root with in/lots in/roads> <out dir> <KR_AGREE>
# KN17 chain rebuilt 21 Nov 2026: kerbgrid --review --road per cell, kerblot --road --cad (no --ground: KN17 had none), comb.py (join + building gate),
# kerbguard --official --zones --drop, kerbface --drop.
K=${K:?set K to the work folder}; D=/home/user/openfetch-derive/openfetch/tools/derive
INP=$1; O=$2; export KR_AGREE=$3; export SUF=$4; mkdir -p $O/gridall $O/work
cell() { x=$1; y=$2; n=${x}_${y}; grep -q RESULT $O/gridall/$n.log 2>/dev/null && return
  W=$O/work/$n; mkdir -p $W/lots $W/roads
  for dx in -1 0 1; do for dy in -1 0 1; do f=$(( (x+dx)*1000 ))_$(( (y+dy)*1000 )).json
    for k in lots roads; do [ -f $INP/in/$k/$f ] && ln -sf $INP/in/$k/$f $W/$k/$f; done; done; done
  cd $W && timeout 1500 python3 $D/kerbgrid.py lots roads $K/in/nsw-traced-raw.json $K/final$SUF $O/gridall/$n.json --box $((x*1000)) $((y*1000)) $((x*1000+1000)) $((y*1000+1000)) --buildings $K/b/bld/$n.json --review --why $O/gridall/$n.why.json --official $K/off/official-all$SUF.json --road $K/igr/igrids3 > $O/gridall/$n.log 2>&1
  rm -rf $W; }
export -f cell; export O INP K D SUF
cat $K/cells.txt | xargs -P 4 -n 2 bash -c 'cell "$0" "$1"'
cd $K && python3 $D/kerblot.py $INP/in/lots $INP/in/roads $K/in/nsw-traced-raw.json $K/drawn$SUF.geojson.gz $K/b/bld $K/cells.txt $O/lot.json --why $O/lot.why.json --road $K/igr/igrids3 --cad $K/in/cad > $O/lot.log 2>&1
cd $K && python3 $D/kn17-run/comb.py $O/gridall $O/lot.json $O/joined.geojson > $O/comb.log 2>&1
python3 $D/kerbguard.py $O/joined.geojson $INP/in/lots $INP/in/roads $K/b/bld $O/guards.json --official $K/off/official-all$SUF.json --zones $K/in/zones --drop $O/guarded.geojson > $O/guard.log 2>&1
zcat -f $O/guarded.geojson > $O/guarded.json; python3 $D/kerbface.py $O/guarded.json $INP/in/lots $INP/in/roads $K/in/cad $O/face.json --drop $O/rings.geojson > $O/face.log 2>&1
python3 -c "import json;F=json.load(open('$O/rings.geojson'))['features'];print('RINGS',len(F))"
