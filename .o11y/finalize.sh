#!/usr/bin/env bash
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME="$ROOT/runtime"
STATUS=${1:-unknown}
TAG=$(cat "$RUNTIME/build-tag" 2>/dev/null || printf '%s' "${GITHUB_RUN_ID:-0}-${GITHUB_JOB:-job}")
START=$(cat "$RUNTIME/build-start" 2>/dev/null || date +%s)
BE="$ROOT/bin/buildevents"

printf '%s\n' "$STATUS" > "$RUNTIME/final-status"

if [ -x "$BE" ] && [ -n "${BUILDEVENT_APIKEY:-}" ] && [ -n "${BUILDEVENT_DATASET:-}" ]; then
  "$BE" build "$TAG" "$START" "$STATUS" > "$RUNTIME/honeycomb-build.txt" 2>&1 \
    || echo "warning: Honeycomb finalization failed; build result is unaffected" >&2
fi

exit 0
