#!/usr/bin/env bash

set -e
set -x

here=$(dirname $0)

# delete files in 'cache' directory not ending in *99.xz
find cache -type f -not -name \*99.xz -delete
