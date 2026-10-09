#!/usr/bin/env bash
# Uploads the repo's static JSON files (data/) into the R2 bucket "holibase-data".
# Usage: bash scripts/upload-data.sh ../data      (path to the repo's data/ folder)
# Afterwards reachable at https://api.holibase.org/data/<path>
set -euo pipefail
SRC="${1:-../data}"
BUCKET="holibase-data"
[ -d "$SRC" ] || { echo "Folder not found: $SRC"; exit 1; }
cd "$SRC"
count=0
while IFS= read -r -d '' f; do
  key="${f#./}"
  npx wrangler r2 object put "$BUCKET/$key" --file "$f" --content-type "application/json" --remote >/dev/null
  count=$((count+1)); (( count % 100 == 0 )) && echo "$count files ..."
done < <(find . -name '*.json' -print0)
echo "Done: $count files uploaded to $BUCKET."
