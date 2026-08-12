#!/usr/bin/env bash
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME="$ROOT/runtime"
BIN="$ROOT/bin"
mkdir -p "$RUNTIME" "$BIN"

if [ ! -s "$RUNTIME/build-start" ]; then
  date +%s > "$RUNTIME/build-start"
fi

TAG="${GITHUB_REPOSITORY:-local}-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-1}-${GITHUB_JOB:-job}"
printf '%s\n' "$TAG" | tr '/ :' '---' > "$RUNTIME/build-tag"

# Honeycomb is deliberately best-effort: build observability must never become
# a new build dependency. When secrets are absent, local structured logs still
# work and the workflow behaves exactly as before.
if [ -n "${BUILDEVENT_APIKEY:-}" ] && [ -n "${BUILDEVENT_DATASET:-}" ]; then
  if command -v curl >/dev/null 2>&1; then
    if curl -fsSL --retry 3 \
      https://github.com/honeycombio/buildevents/releases/latest/download/buildevents-linux-amd64 \
      -o "$BIN/buildevents"; then
      chmod +x "$BIN/buildevents"
      if [ -n "${GITHUB_PATH:-}" ]; then
        printf '%s\n' "$BIN" >> "$GITHUB_PATH"
      fi
      echo "Honeycomb buildevents enabled"
    else
      rm -f "$BIN/buildevents"
      echo "warning: Honeycomb buildevents download failed; continuing with local logs" >&2
    fi
  fi
fi

# Sentry is also optional. Install its SDK into an isolated venv only when a
# DSN is configured. A failed telemetry install is diagnostic-only.
if [ -n "${SENTRY_DSN:-}" ] && command -v python >/dev/null 2>&1; then
  if python -m venv "$ROOT/.venv" >/dev/null 2>&1; then
    "$ROOT/.venv/bin/python" -m pip install --quiet --disable-pip-version-check sentry-sdk \
      || echo "warning: Sentry SDK install failed; local failure JSON will still be written" >&2
  fi
fi

exit 0
