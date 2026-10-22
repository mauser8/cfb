#!/usr/bin/env python3
"""CLI helper: fetch ESPN, write a local JSON snapshot. The live plugin uses src/transform.py."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from transform import build, fetch, run  # noqa: E402


def main():
    print("Fetching FBS scoreboard from ESPN...")
    payload = run({})
    if payload.get("error"):
        print(f"error: {payload['error']}", file=sys.stderr)
        try:
            raw = fetch()
            print(f"  raw payload: {len(json.dumps(raw)) / 1024:.1f} KB")
            payload = build(raw)
        except Exception:
            sys.exit(1)

    print(f"  {len(payload['games'])} games after filter/sort")
    compact = json.dumps(payload, separators=(",", ":"))
    for path in ("data/schedule.json", "docs/schedule.json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(compact)
        print(f"  wrote {path} ({os.path.getsize(path) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
