#!/usr/bin/env python3
"""Persist CI failure context locally and optionally report it to Sentry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
MAX_LOG_CHARS = 12000


def tail(path: Path) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"<unable to read {path.name}: {exc}>"
    return data[-MAX_LOG_CHARS:]


def github_context() -> dict[str, str]:
    keys = (
        "GITHUB_REPOSITORY",
        "GITHUB_WORKFLOW",
        "GITHUB_JOB",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_SHA",
        "GITHUB_REF",
        "GITHUB_EVENT_NAME",
        "RUNNER_OS",
        "RUNNER_ARCH",
    )
    return {key.lower(): os.getenv(key, "") for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default=os.getenv("GITHUB_JOB", "unknown"))
    args = parser.parse_args()

    RUNTIME.mkdir(parents=True, exist_ok=True)
    logs = {path.name: tail(path) for path in sorted(RUNTIME.glob("*.log"))}
    payload: dict[str, Any] = {
        "kind": "github-actions-failure",
        "job": args.job,
        "github": github_context(),
        "logs": logs,
    }
    destination = RUNTIME / f"failure-{args.job}.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote structured failure context to {destination}")

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        print("SENTRY_DSN is not configured; skipping remote Sentry event")
        return 0

    try:
        import sentry_sdk  # type: ignore
    except Exception as exc:
        print(f"Sentry SDK unavailable; local failure context retained: {exc}")
        return 0

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment="github-actions",
            release=os.getenv("GITHUB_SHA") or None,
            send_default_pii=False,
        )
        for key, value in payload["github"].items():
            if value:
                sentry_sdk.set_tag(key, value)
        sentry_sdk.set_tag("ci_job", args.job)
        sentry_sdk.set_context("github_actions", payload["github"])
        sentry_sdk.set_context("captured_step_logs", logs)
        event_id = sentry_sdk.capture_message(
            f"CachyOS ISO CI failure in {args.job}", level="error"
        )
        sentry_sdk.flush(timeout=5)
        print(f"reported Sentry event: {event_id}")
    except Exception as exc:
        print(f"warning: Sentry reporting failed; build result is unaffected: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
