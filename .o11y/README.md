# CI observability

This directory contains **best-effort diagnostics** for the offline ISO build. Telemetry is deliberately outside the correctness path: Honeycomb or Sentry outages, missing credentials, or SDK/download failures must never change the build result.

## Local diagnostics

`.o11y/run-step.sh` captures the output, duration, and exit code of high-risk build stages under `.o11y/runtime/`. Failure JSON and captured logs are uploaded as GitHub Actions artifacts even when remote telemetry is disabled.

## Honeycomb traces

Set these GitHub Actions repository secrets to enable Honeycomb Buildevents traces:

- `HONEYCOMB_API_KEY`
- `HONEYCOMB_DATASET`

`.o11y/setup.sh` downloads the maintained `honeycombio/buildevents` Linux binary only when both values are present. `.o11y/run-step.sh` then emits command spans and `.o11y/finalize.sh` closes the build trace.

## Sentry failure events

Set this repository secret to enable Sentry reporting:

- `SENTRY_DSN`

When configured, setup creates an isolated Python virtual environment and installs `sentry-sdk`. On a failed job, `.o11y/report_failure.py` sends one error event containing GitHub Actions metadata and bounded tails of the captured step logs. The same data is always retained locally as JSON.

## Design rule

Observability is for diagnosis and trend visibility, **not for hiding or retrying failures**. Build commands still fail closed and propagate their original exit codes.
