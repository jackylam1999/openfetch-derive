cd "${1:-lidar2}"
for j in 92297 92303 92307 92312; do
  for i in 1 2 3 4; do curl -sSf -C - -o DATA_$j.zip https://elvis-downloads.s3.amazonaws.com/DATA_$j.zip && break; sleep $((i*5)); done
  echo got $j $(stat -c %s DATA_$j.zip)
done
echo ALLDONE
