"""
TRMNL serverless transform for college football scores.

Polling ESPN from TRMNL's poller fails: the scoreboard is ~1MB (100KB cap)
and ESPN often 403s browser-like cloud clients. This run() fetches ESPN
itself, keeps a handful of fields, and returns merge variables for Liquid.

Must stay under ~5 seconds (TRMNL serverless limit).
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

PRIMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "football/college-football/scoreboard"
)
FALLBACK_URL = PRIMARY_URL.replace("site.api.", "site.web.api.")

# groups=80 = every FBS game, not just ranked. limit=100 covers a full Saturday.
PARAMS = "groups=80&limit=100"
HEADERS = {
    "User-Agent": "trmnl-cfb-plugin/1.1",
    "Accept": "application/json",
}

MAX_GAMES = 12
FETCH_TIMEOUT = 3.5


def _get(url):
    req = urllib.request.Request(f"{url}?{PARAMS}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return json.load(resp)


def fetch():
    last_err = None
    for url in (PRIMARY_URL, FALLBACK_URL):
        try:
            return _get(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
    raise RuntimeError(f"ESPN scoreboard unavailable: {last_err}")


def normalize_rank(competitor):
    rank = competitor.get("rank")
    if rank is None:
        rank = (competitor.get("curatedRank") or {}).get("current")
    if rank in (None, 99, "99"):
        return None
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def slim_team(competitor):
    team = competitor.get("team") or {}
    records = [
        r for r in (competitor.get("records") or [])
        if r.get("type") == "total"
    ]
    return {
        "abbr": team.get("abbreviation") or "?",
        "name": team.get("shortDisplayName") or team.get("displayName") or "Team",
        "rank": normalize_rank(competitor),
        "record": records[0].get("summary") if records else "",
        "score": str(competitor.get("score") or "0"),
        "logo": team.get("logo") or "",
    }


def filter_event(event):
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None

    by_side = {c.get("homeAway"): c for c in competitors}
    away = slim_team(by_side.get("away") or competitors[1])
    home = slim_team(by_side.get("home") or competitors[0])

    status = event.get("status") or comp.get("status") or {}
    status_type = status.get("type") or {}
    broadcasts = comp.get("broadcasts") or []
    names = broadcasts[0].get("names") if broadcasts else None

    return {
        "state": status_type.get("state") or "pre",
        "detail": status_type.get("shortDetail") or "",
        "broadcast": (names[0] if names else None) or "",
        "date": event.get("date") or "",
        "away": away,
        "home": home,
    }


def _kickoff(game):
    raw = game.get("date") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def sort_key(game):
    """Live, then next kickoff, then finals. Ranked matchups win ties."""
    ranks = sorted(r for r in (game["away"].get("rank"), game["home"].get("rank")) if r)
    rank_boost = ranks[0] if ranks else 999
    kickoff = _kickoff(game)
    state = game["state"]
    if state == "in":
        return (0, rank_boost, kickoff)
    if state == "pre":
        return (1, kickoff, rank_boost)
    return (2, -kickoff.timestamp(), rank_boost)


def build(raw):
    games = [g for g in (filter_event(e) for e in raw.get("events") or []) if g]
    games.sort(key=sort_key)
    week = raw.get("week") or {}
    return {
        "week_number": week.get("number"),
        "games": games[:MAX_GAMES],
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": "",
    }


def run(input):
    """Fetch ESPN live. If that fails, keep games already polled from GitHub."""
    try:
        return build(fetch())
    except Exception as e:
        if input.get("games"):
            return input
        return {
            "week_number": None,
            "games": [],
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "error": str(e),
        }
