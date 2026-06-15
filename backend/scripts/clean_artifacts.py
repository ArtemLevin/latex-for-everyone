#!/usr/bin/env python3
"""Safe Latexed artifact cleanup CLI.

Default mode is dry-run so operators can inspect the exact cleanup report before
passing --commit in cron/systemd timers or local maintenance scripts.
"""
import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services.artifact_cleanup import cleanup_configured_artifacts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely clean Latexed runtime artifacts from trusted roots.")
    parser.add_argument("--commit", action="store_true", help="Delete matching stale artifacts. Without this flag, only report candidates.")
    parser.add_argument("--max-age-seconds", type=int, default=settings.ARTIFACT_TTL_SECONDS, help="Retention age threshold; <=0 disables cleanup.")
    args = parser.parse_args()

    reports = cleanup_configured_artifacts(dry_run=not args.commit, max_age_seconds=args.max_age_seconds)
    print(json.dumps([report.to_dict() for report in reports], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
