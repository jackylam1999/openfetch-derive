#!/bin/bash
# evalft.sh model.pt tag : prob squares for Carlton + North Melbourne with the model, rerun both, council-kerb checks
export KERB_SPLAY_FAR=0; M=$1; T=$2; cd /tmp/claude-0/w/in; D=/tmp/claude-0/w/derive/openfetch/tools/derive
mkdir -p prob_$T; (cd $D/kerbvic && python3 -W ignore aerroad.py predict /tmp/claude-0/w/in/prob_$T $M /tmp/claude-0/w/in/cellsCN.txt > /tmp/claude-0/w/in/pred_$T.log 2>&1)
for s in carlton northmelb; do KERB_AER=prob_$T python3 -W ignore /tmp/claude-0/w/tools/joins.py prep/$s e_$T/$s > e_$T-$s.log 2>&1 & done; wait
for s in carlton northmelb; do echo "== $s $T"; python3 -W ignore $D/kerbvic/study/truthcmp.py e_$T/$s/rings.json com-kerbs.json | head -1; python3 /tmp/claude-0/w/tools/raytruth.py e_$T/$s/sides.json com-kerbs.json bays.geojson | grep -v "prob at"; done
