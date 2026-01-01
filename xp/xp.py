import asyncio
import json
import os
import random
import tempfile
import time
from typing import Any, Dict, List, Optional

_file_lock = asyncio.Lock()


def _default_stats_path() -> str:
    return os.path.join(os.path.dirname(__file__), "stats.json")


def _load_stats(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        # convert dict of id -> entry to list
        data = list(data.values())

    if not isinstance(data, list):
        raise ValueError("stats.json must contain a list or object of entries")

    # normalize numeric fields
    cleaned: List[Dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            entry["level"] = int(entry.get("level", 0))
        except Exception:
            entry["level"] = 0
        try:
            entry["xp"] = int(entry.get("xp", 0))
        except Exception:
            entry["xp"] = 0
        # last_xp stored as float epoch seconds
        try:
            entry["last_xp"] = float(entry.get("last_xp", 0))
        except Exception:
            entry["last_xp"] = 0.0

        cleaned.append(entry)

    return cleaned


def _write_stats_atomic(path: str, data: List[Dict[str, Any]]) -> None:
    # Try to preserve list format on write
    dirpath = os.path.dirname(path) or "."
    tf = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dirpath, prefix=".stats_json_")
        tf = os.fdopen(fd, "w", encoding="utf-8")
        json.dump(data, tf, indent=2, ensure_ascii=False)
        tf.flush()
        os.fsync(tf.fileno())
        tf.close()
        tf = None
        os.replace(tmp_path, path)
    finally:
        if tf is not None:
            try:
                tf.close()
            except Exception:
                pass


async def maybe_award_xp(message: Any, stats_path: Optional[str] = None) -> Dict[str, Any]:
    """Possibly award XP for a message.

    Parameters
    - message: discord.Message-like object with `.author.id` (or `.author` object) and optionally `.author.name`.
    - stats_path: optional path to stats.json; defaults to the file next to this module.

    Behavior
    - Awards a random amount between 10 and 15 XP if the last XP for that user was more than 60 seconds ago.
    - If xp >= int(level**1.5 * 50), increases level by 1 and subtracts that threshold from xp. Repeats while possible.
    - Persists changes to `stats.json` atomically under an asyncio lock to reduce write races.

    Returns a dict: {"awarded": bool, "xp_added": int, "levels_gained": int, "new_level": int, "new_xp": int}
    """
    if stats_path is None:
        stats_path = _default_stats_path()

    # Resolve author id
    try:
        user_id = str(message.author.id)
    except Exception:
        # allow passing an object with 'author' being an id string directly for tests
        user_id = str(getattr(message, "author", message))

    async with _file_lock:
        stats = _load_stats(stats_path)

        # find entry by id (search list for 'id' field)
        entry = None
        for e in stats:
            if str(e.get("id")) == user_id:
                entry = e
                break

        if entry is None:
            entry = {"id": user_id, "level": 0, "xp": 0, "last_xp": 0.0}
            stats.append(entry)

        now = time.time()
        last = float(entry.get("last_xp", 0.0) or 0.0)
        result = {"awarded": False, "xp_added": 0, "levels_gained": 0, "new_level": entry["level"], "new_xp": entry["xp"]}

        if now - last >= 60:
            add = random.randint(10, 15)
            entry["xp"] = int(entry.get("xp", 0)) + add
            entry["last_xp"] = now
            result["awarded"] = True
            result["xp_added"] = add

            # level up while xp meets threshold
            gained = 0
            while True:
                level = int(entry.get("level", 0))
                threshold = int(level ** 1.5 * 50)
                # if level==0 threshold is 0 -> avoid infinite loop: set base threshold for level 0 -> 50
                if level == 0:
                    threshold = 50

                if entry["xp"] >= threshold and threshold > 0:
                    entry["xp"] -= threshold
                    entry["level"] = level + 1
                    gained += 1
                else:
                    break

            result["levels_gained"] = gained
            result["new_level"] = int(entry.get("level", 0))
            result["new_xp"] = int(entry.get("xp", 0))

        # persist
        _write_stats_atomic(stats_path, stats)

    return result


if __name__ == "__main__":
    # small non-discord simulation / smoke test using a temporary stats file
    class FakeAuthor:
        def __init__(self, id_):
            self.id = id_

    class FakeMessage:
        def __init__(self, author):
            self.author = author

    async def _test():
        fd, tmp = tempfile.mkstemp(prefix="test_stats_", suffix=".json")
        os.close(fd)
        try:
            # initial stats: one user
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([{"id": "user1", "level": 0, "xp": 0, "last_xp": 0}], f)

            msg = FakeMessage(FakeAuthor("user1"))
            print("First award (should grant XP):")
            res1 = await maybe_award_xp(msg, stats_path=tmp)
            print(res1)

            print("Immediate second award (should not grant XP):")
            res2 = await maybe_award_xp(msg, stats_path=tmp)
            print(res2)

            # simulate passage of time by setting last_xp far in the past
            with open(tmp, "r+", encoding="utf-8") as f:
                s = json.load(f)
                s[0]["last_xp"] = 0
                f.seek(0)
                json.dump(s, f, indent=2)
                f.truncate()

            print("After simulating time passage (should grant XP):")
            res3 = await maybe_award_xp(msg, stats_path=tmp)
            print(res3)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass

    asyncio.run(_test())
