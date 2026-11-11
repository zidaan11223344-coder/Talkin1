"""Independent persistent state for Talkin1 royal hunt events."""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path

ROYAL_DRAGON_VALUE = 2_000_000_000
ROYAL_DIAMOND_VALUE = 4_000_000_000

class RoyalHuntStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"players": {}, "history": []}
        except (OSError, ValueError, TypeError):
            return {"players": {}, "history": []}

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _key(user_id, username):
        value = str(user_id or username or "").strip().lstrip("@")
        return value or f"name:{str(username or '').strip().casefold()}"

    def add(self, user_id, username, item: str, room: str = ""):
        with self.lock:
            data = self._load(); players = data.setdefault("players", {})
            key = self._key(user_id, username)
            player = players.setdefault(key, {"username": str(username or key), "dragon": 0, "diamond": 0, "animals": {}})
            player["username"] = str(username or player.get("username") or key).lstrip("@")
            if item == "royal_dragon": player["dragon"] = int(player.get("dragon", 0) or 0) + 1
            elif item == "royal_diamond": player["diamond"] = int(player.get("diamond", 0) or 0) + 1
            else:
                animals = player.setdefault("animals", {}); animals[item] = int(animals.get(item, 0) or 0) + 1
            data.setdefault("history", []).append({"at": int(time.time()), "user": key, "username": player["username"], "item": item, "room": str(room or "")})
            data["history"] = data["history"][-1000:]
            self._save(data)
            return dict(player)

    def inventory(self, user_id, username):
        with self.lock:
            p = self._load().get("players", {}).get(self._key(user_id, username), {})
            return dict(p) if isinstance(p, dict) else {}

    def top(self, limit=10):
        with self.lock:
            rows = []
            for p in self._load().get("players", {}).values():
                if not isinstance(p, dict): continue
                rows.append((int(p.get("diamond", 0) or 0), int(p.get("dragon", 0) or 0), str(p.get("username", ""))))
            return sorted(rows, key=lambda x: (x[0] + x[1], x[0], x[1]), reverse=True)[:limit]

    def top_diamonds(self, limit=10):
        with self.lock:
            rows = []
            for p in self._load().get("players", {}).values():
                if not isinstance(p, dict): continue
                count = int(p.get("diamond", 0) or 0)
                if count > 0: rows.append((count, str(p.get("username", ""))))
            return sorted(rows, key=lambda x: (x[0], x[1].casefold()), reverse=True)[:limit]

    def top_dragons(self, limit=10):
        with self.lock:
            rows = []
            for p in self._load().get("players", {}).values():
                if not isinstance(p, dict): continue
                count = int(p.get("dragon", 0) or 0)
                if count > 0: rows.append((count, str(p.get("username", ""))))
            return sorted(rows, key=lambda x: (x[0], x[1].casefold()), reverse=True)[:limit]

    def sell(self, user_id, username, item: str, amount: int):
        amount = max(1, int(amount or 1))
        with self.lock:
            data = self._load(); key = self._key(user_id, username); p = data.setdefault("players", {}).setdefault(key, {})
            field = "dragon" if item == "royal_dragon" else "diamond"
            count = int(p.get(field, 0) or 0)
            sold = min(count, amount)
            if sold <= 0: return {"ok": False, "count": count, "sold": 0, "value": 0}
            p[field] = count - sold
            value = sold * (ROYAL_DRAGON_VALUE if field == "dragon" else ROYAL_DIAMOND_VALUE)
            self._save(data)
            return {"ok": True, "count": p[field], "sold": sold, "value": value}
