#!/usr/bin/env/bash

USERNAME_BULK=usernames_bulk
USERNAME_OUT=usernames_2019-11-16

# TODO:
# - this could be parallelized
# - OR, just extract usernames during the download process and keep a running list
time for f in cache/*; do
    xz -dc $f | jq -r .by | sort -n >> usernames_bulk;
done

# Reform:
time sort -n "$USERNAME_BULK" |uniq -c > "$USERNAME_OUT"
sort -rn "$USERNAME_OUT" > "$USERNAME_OUT"-sorted
time awk '{print $2}' "$USERNAME_OUT" > "$USERNAME_OUT"-names-only
# delete 'null'
run ./import.py -u "$USERNAME_OUT"-names-only -c 20
