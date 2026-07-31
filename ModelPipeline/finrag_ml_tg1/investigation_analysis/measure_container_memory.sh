#!/usr/bin/env bash
# Sample container memory while issuing real queries against the local stack.
# Purpose: derive the Fargate task cpu/memory from observation, not estimate.
set -u
OUT="$(dirname "$0")"

sample() {
    # $1 = label, runs until the marker file is removed
    while [ -f "$OUT/sampling" ]; do
        docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' \
            | sed "s/^/$1 /" >> "$OUT/stats_raw.log"
    done
}

run_query() {
    local label="$1" ; local question="$2"
    echo "=== $label ===" >> "$OUT/queries.log"
    touch "$OUT/sampling"
    sample "$label" &
    local sp=$!
    local t0=$(date +%s)
    curl -s -X POST localhost:8000/query \
        -H 'Content-Type: application/json' \
        -d "$(jq -n --arg q "$question" '{question:$q}')" \
        -o "$OUT/resp_${label}.json" -w 'http=%{http_code} time=%{time_total}\n' \
        >> "$OUT/queries.log" 2>&1
    local t1=$(date +%s)
    rm -f "$OUT/sampling"
    wait $sp 2>/dev/null
    echo "wall=$((t1-t0))s" >> "$OUT/queries.log"
}

: > "$OUT/stats_raw.log"
: > "$OUT/queries.log"

run_query "simple" "What was Apple's total revenue in 2021?"
sleep 3
run_query "heavy" "Compare revenue growth, operating margin, R&D spending and total debt across Apple, Microsoft, Amazon, Alphabet, Meta, Nvidia, Tesla, Intel, Cisco and Oracle, and summarise the principal risk factors, liquidity position, and management outlook that each company disclosed."

echo "DONE" >> "$OUT/queries.log"
