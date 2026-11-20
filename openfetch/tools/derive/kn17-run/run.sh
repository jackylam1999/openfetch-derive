#!/bin/bash
K=$(cd $(dirname $0); pwd); x=$1; y=$2; n=${x}_${y}
grep -q RESULT $K/gridall/$n.log 2>/dev/null && exit 0
W=$K/work/$n; mkdir -p $W/lots $W/roads
for dx in -1 0 1; do for dy in -1 0 1; do f=$(( (x+dx)*1000 ))_$(( (y+dy)*1000 )).json
  for k in lots roads; do [ -f $K/in/$k/$f ] && ln -sf $K/in/$k/$f $W/$k/$f; done; done; done
cd $W && timeout 1500 python3 /home/user/openfetch-derive/openfetch/tools/derive/kerbgrid.py lots roads $K/nsw-traced-raw.json $K/final $K/gridall/$n.json --box $((x*1000)) $((y*1000)) $((x*1000+1000)) $((y*1000+1000)) --buildings $K/b/bld/$n.json --review --why $K/gridall/$n.why.json --official $K/off/official-all.json --road $K/igr > $K/gridall/$n.log 2>&1
