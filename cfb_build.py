#!/usr/bin/env python3
"""
College Football Schedule Builder
Fetches ESPN FBS scoreboard data, filters to minimal JSON, writes to
data/ and docs/ so GitHub Pages can serve it to a TRMNL private plugin.

Two reasons this relay exists rather than polling ESPN directly:
  1. ESPN 403s browser-like clients from cloud IPs, TRMNL's poller included.
  2. The raw CFB payload is ~400KB; TRMNL caps polling responses at 100KB.
"""

import json
import os
import sys
from datetime import datetime, UTC

import requests

PRIMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "football/college-football/scoreboard"
)
# Mirror ESPN uses internally; used as a fallback if the primary 403s.
FALLBACK_URL = PRIMARY_URL.replace("site.api.", "site.web.api.")

# groups=80 -> every FBS game, not just ranked teams
# limit=500 -> default cap is 100, a full Saturday can exceed it
PARAMS = {"groups": 80, "limit": 500}

# Non-browser UA. ESPN started rejecting "Mozilla/5.0" from cloud IPs in Aug 2026.
HEADERS = {
    "User-Agent": "trmnl-cfb-relay/1.0 (+https://github.com/)",
    "Accept": "application/json",
}

MAX_EVENTS = 80
SOFT_LIMIT_KB = 90


def fetch():
    for url in (PRIMARY_URL, FALLBACK_URL):
        try:
            r = requests.get(url, params=PARAMS, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  {url} failed: {e}", file=sys.stderr)
    return None


def normalize_rank(competitor):
    """ESPN has used both `rank` and `curatedRank.current`. 99 means unranked."""
    rank = competitor.get("rank")
    if rank is None:
        rank = (competitor.get("curatedRank") or {}).get("current")
    if rank in (None, 99):
        return None
    try:
        return int(rank)
    except (TypeError, ValueError):
        return None


def filter_event(event):
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None

    notes = comp.get("notes") or []
    broadcasts = comp.get("broadcasts") or []
    links = event.get("links") or []

    broadcast = None
    if broadcasts:
        names = broadcasts[0].get("names") or []
        broadcast = names[0] if names else None

    return {
        "id": event.get("id"),
        "shortName": event.get("shortName"),
        "date": event.get("date"),
        "headline": notes[0].get("headline") if notes else None,
        "broadcast": broadcast,
        "venue": (comp.get("venue") or {}).get("fullName"),
        "link": links[0].get("href") if links else None,
        "status": event.get("status") or comp.get("status") or {},
        "competitions": [{
            "competitors": [
                {
                    "homeAway": c.get("homeAway"),
                    "score": c.get("score"),
                    "rank": normalize_rank(c),
                    "winner": c.get("winner"),
                    # only the total record; ESPN also sends home/away/conf splits
                    "records": [
                        r for r in (c.get("records") or [])
                        if r.get("type") == "total"
                    ][:1],
                    "team": {
                        "abbreviation": (c.get("team") or {}).get("abbreviation"),
                        "displayName": (c.get("team") or {}).get("displayName"),
                        "shortDisplayName": (c.get("team") or {}).get("shortDisplayName"),
                        "logo": (c.get("team") or {}).get("logo"),
                    },
                }
                for c in competitors[:2]
            ]
        }],
    }


def sort_key(event):
    """Live first, then ranked-vs-ranked, then ranked-vs-unranked, then the rest."""
    state = ((event.get("status") or {}).get("type") or {}).get("state")
    teams = event["competitions"][0]["competitors"]
    ranks = sorted(r for r in (t.get("rank") for t in teams) if r)

    if state == "in":
        bucket = 0
    elif len(ranks) >= 2:
        bucket = 1
    elif len(ranks) == 1:
        bucket = 2
    else:
        bucket = 3

    return (bucket, ranks[0] if ranks else 999, event.get("date") or "")


def build(data):
    events = [e for e in (filter_event(e) for e in data.get("events", [])) if e]
    events.sort(key=sort_key)

    trimmed = events[:MAX_EVENTS]
    while len(trimmed) > 20:
        size_kb = len(json.dumps(trimmed, separators=(",", ":"))) / 1024
        if size_kb <= SOFT_LIMIT_KB:
            break
        trimmed.pop()

    return {
        "season": data.get("season", {}),
        "week": data.get("week", {}),
        "events": trimmed,
        "generated": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def save(payload, path, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=indent, separators=(",", ":") if not indent else None)
    print(f"  wrote {path} ({os.path.getsize(path) / 1024:.1f} KB)")


def main():
    print("Fetching FBS scoreboard from ESPN...")
    raw = fetch()
    if not raw:
        print("No data; leaving existing files untouched")
        sys.exit(1)

    print(f"  raw payload: {len(json.dumps(raw)) / 1024:.1f} KB")
    payload = build(raw)
    print(f"  {len(payload['events'])} events after filter/sort")

    save(payload, "data/schedule.json")
    save(payload, "docs/schedule.json")   # compact - this is what TRMNL polls

    if not payload["events"]:
        print("Note: zero events. Offseason, or ESPN returned an empty slate.")


if __name__ == "__main__":
    main()