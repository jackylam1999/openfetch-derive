#!/bin/bash
K=${K:?set K to the work folder}; x=$1; y=$2; n=${x}_${y}
grep -q RESULT $K/gridall/$n.log 2>/dev/null && exit 0
cd $K/in && timeout 1200 python3 $K/code/openfetch/tools/derive/kerbgrid.py lots roads nsw-traced-raw.json $K/final $K/gridall/$n.json --box $((x*1000)) $((y*1000)) $((x*1000+1000)) $((y*1000+1000)) --buildings $K/grid/bld/$n.json --review --why $K/gridall/$n.why.json > $K/gridall/$n.log 2>&1
