#!/usr/bin/env bash
# End-to-end check that every page and API endpoint answers with real data.
#
#   scripts/dev.sh start && scripts/smoke.sh
set -uo pipefail

WEB="${SPLM_WEB_URL:-http://127.0.0.1:3000}"
fail=0

check_page() {
  local path="$1"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' "$WEB$path" || echo 000)
  if [ "$code" = "200" ]; then
    printf '  %-16s %s\n' "$path" "$code"
  else
    printf '  %-16s %s  FAIL\n' "$path" "$code"
    fail=1
  fi
}

check_get() {
  local path="$1" expect="$2"
  local body
  body=$(curl -s --max-time 120 "$WEB$path" || echo '')
  if printf '%s' "$body" | grep -q "$expect"; then
    printf '  %-26s ok\n' "$path"
  else
    printf '  %-26s FAIL (no %s)\n' "$path" "$expect"
    fail=1
  fi
}

check_post() {
  local path="$1" payload="$2" expect="$3"
  local body
  body=$(curl -s --max-time 180 -X POST "$WEB$path" \
    -H 'Content-Type: application/json' -d "$payload" || echo '')
  if printf '%s' "$body" | grep -q "$expect"; then
    printf '  %-26s ok\n' "$path"
  else
    printf '  %-26s FAIL (no %s)\n' "$path" "$expect"
    fail=1
  fi
}

echo 'pages'
for path in / /phrase-dna /inspector /context /multilingual /benchmark /ablation /architecture /system; do
  check_page "$path"
done

echo 'api'
check_get  /api/system              '"model_id"'
check_get  /api/presets             '"presets"'
check_get  /api/benchmark/results   '"results"'
check_post /api/analyze  '{"text":"John will meet Sarah in Paris tomorrow."}'            '"phrase_frame"'
check_post /api/compare  '{"prompt":"John will meet Sarah in","display_k":5}'            '"semantic_focus"'
check_post /api/predict/base '{"prompt":"John will meet Sarah in","display_k":5}'        '"candidates"'
check_post /api/context  '{"text":"John met Sarah in Paris. She gave him a document."}'  '"coreferences"'
check_post /api/multilingual '{"texts":{"en":"John is in Paris.","fr":"John est à Paris.","vi":"John đang ở Paris."}}' '"agreement"'
check_post /api/ablation '{"prompt":"John will meet Sarah in","cumulative":true}'        '"runs"'
check_post /api/generate/compare '{"prompt":"John will meet Sarah in","max_new_tokens":6}' '"continuation"'

if [ "$fail" = 0 ]; then
  echo 'all checks passed'
else
  echo 'some checks FAILED' >&2
fi
exit "$fail"
