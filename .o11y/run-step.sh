#!/usr/bin/env bash
set -uo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME="$ROOT/runtime"
mkdir -p "$RUNTIME"

NAME=${1:?step name required}
shift
if [ "${1:-}" = "--" ]; then
  shift
fi
if [ "$#" -eq 0 ]; then
  echo "run-step: command required" >&2
  exit 64
fi

SAFE_NAME=$(printf '%s' "$NAME" | tr -cs 'A-Za-z0-9_.-' '_')
LOG="$RUNTIME/${SAFE_NAME}.log"
START=$(date +%s)
TAG=$(cat "$RUNTIME/build-tag" 2>/dev/null || printf '%s' "${GITHUB_RUN_ID:-0}-${GITHUB_JOB:-job}")
BE="$ROOT/bin/buildevents"

set +e
if [ -x "$BE" ] && [ -n "${BUILDEVENT_APIKEY:-}" ] && [ -n "${BUILDEVENT_DATASET:-}" ]; then
  "$BE" cmd "$TAG" 0 "$NAME" -- "$@" 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
else
  "$@" 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
fi
set -e

END=$(date +%s)
printf '{"name":"%s","started":%s,"ended":%s,"exit_code":%s}\n' \
  "$SAFE_NAME" "$START" "$END" "$RC" > "$RUNTIME/${SAFE_NAME}.json"

exit "$RC"
