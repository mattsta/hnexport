#!/usr/bin/env bash

set -e
set -x

file=$1
jq -r 'del(.submitted) | keys | @csv' $1
jq -r 'del(.submitted) | [.[]] | @csv' $1
