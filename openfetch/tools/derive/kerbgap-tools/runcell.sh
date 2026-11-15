#!/bin/bash
S=/tmp/claude-0/-home-user/17bc20c6-45f6-5bb3-8440-d43306115c12/scratchpad/k; D=$S/code/openfetch/tools/derive
x=$1; y=$2; n=${x}_${y}; X0=$((x*1000)); Y0=$((y*1000))
[ -s $S/cells/$n.json ] && exit 0
cd $S/in && timeout 1800 python3 $D/kerbgap.py nsw-r11.json lots roads $S/cells/$n.json --fuse-with nsw-traced-raw.json \
  --box $((X0-250)) $((Y0-250)) $((X0+1250)) $((Y0+1250)) --core $X0 $Y0 $((X0+1000)) $((Y0+1000)) \
  --main-seen --official $S/parra-off.json --why $S/cells/$n.why.json --loops-cache $S/cells/$n.pkl > $S/cells/$n.log 2>&1
