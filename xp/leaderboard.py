import json
import os
from typing import Any, Dict, List


def _get_stats_path() -> str:
    """Return the absolute path to stats.json located next to this file."""
    return os.path.join(os.path.dirname(__file__), "stats.json")


def _load_stats(path: str) -> List[Dict[str, Any]]:
    """Load stats.json and normalize to a list of dicts with numeric level/xp."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Accept either a list of objects or a dict of id -> object
    if isinstance(data, dict):
        data = list(data.values())

    if not isinstance(data, list):
        raise ValueError("stats.json must contain a list or object of entries")

    cleaned: List[Dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        # coerce level/xp to ints (safe fallback to 0)
        try:
            level = int(entry.get("level", 0))
        except Exception:
            level = 0
        try:
            xp = int(entry.get("xp", 0))
        except Exception:
            xp = 0

        entry["level"] = level
        entry["xp"] = xp
        cleaned.append(entry)

    return cleaned


def leaderboard(length: int):
    """From stats.json, generate the n people with the most levels then the most xp"""
    stats_path = _get_stats_path()
    data = _load_stats(stats_path)

    # Sort by levels first, then by XP
    sorted_data = sorted(data, key=lambda x: (x["level"], x["xp"]), reverse=True)

    return sorted_data[:length]


def main() -> None:
    # small smoke test / demo
    from pprint import pprint

    pprint(leaderboard(3))


if __name__ == '__main__':
    main()