#!/bin/bash
S=${S:?set S to the work folder holding in/, cells/ and parra-off.json}; D=${D:?set D to openfetch/tools/derive}
OUT=${OUT:-cells}; EXTRA=${EXTRA:-}; mkdir -p $S/$OUT; [ -f $S/$OUT/${1}_${2}.pkl ] || cp $S/cells/${1}_${2}.pkl $S/$OUT/ 2>/dev/null
x=$1; y=$2; n=${x}_${y}; X0=$((x*1000)); Y0=$((y*1000))
grep -q RESULT $S/$OUT/${1}_${2}.log 2>/dev/null && exit 0
cd $S/in && timeout 3000 python3 $D/kerbgap.py nsw-r11.json lots roads $S/$OUT/$n.json --fuse-with nsw-traced-raw.json   --box $((X0-250)) $((Y0-250)) $((X0+1250)) $((Y0+1250)) --core $X0 $Y0 $((X0+1000)) $((Y0+1000))   --main-seen $EXTRA --official $S/parra-off.json --why $S/$OUT/$n.why.json --loops-cache $S/$OUT/$n.pkl > $S/$OUT/$n.log 2>&1
