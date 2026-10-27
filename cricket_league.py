"""Persistent Cricket World Cup registration and bracket scheduler."""
from __future__ import annotations

import copy
import random
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from cricket_state import JsonState, normalize


class CricketLeague:
    TEAM_SIZE = 4
    MAX_TEAMS = 16
    QUALIFYING_PRIZE = 1_000_000_000
    FINAL_PRIZE = 100_000_000_000

    def __init__(self, path: str | Path, persist=None, match_hour: int = 20):
        self.state = JsonState(path, self._blank, persist=persist)
        self.match_hour = max(0, min(23, int(match_hour)))

    @staticmethod
    def _blank():
        return {"version": 1, "status": "registration", "teams": {}, "matches": [], "opened_at": 0}

    @staticmethod
    def _team_key(name):
        return normalize(name)

    def register(self, team_name, room, players):
        name = str(team_name or "").strip()
        room = str(room or "").strip()
        players = [str(p or "").strip().lstrip("@") for p in players if str(p or "").strip()]
        if not name or not room or len(players) != self.TEAM_SIZE or len({self._team_key(p) for p in players}) != self.TEAM_SIZE:
            return {"ok": False, "error": "الصيغة تتطلب اسم الفريق والغرفة وأربعة لاعبين مختلفين."}
        key = self._team_key(name)
        def mutate(data):
            if data.get("status") not in {"registration", "ready"}:
                return {"ok": False, "error": "الدوري بدأ بالفعل؛ لا يمكن التسجيل الآن."}
            if key not in data.setdefault("teams", {}) and len(data["teams"]) >= self.MAX_TEAMS:
                return {"ok": False, "error": f"اكتمل الحد الأقصى للدوري ({self.MAX_TEAMS} فريقًا)."}
            data["teams"][key] = {"name": name, "room": room, "players": players, "registered_at": int(time.time())}
            data["status"] = "ready" if len(data["teams"]) >= 2 else "registration"
            return {"ok": True, "team": copy.deepcopy(data["teams"][key]), "count": len(data["teams"])}
        return self.state.mutate(mutate)

    def change_room(self, team_name, room):
        key = self._team_key(team_name)
        room = str(room or "").strip()
        def mutate(data):
            team = data.setdefault("teams", {}).get(key)
            if not team:
                return {"ok": False, "error": "الفريق غير مسجل."}
            team["room"] = room
            return {"ok": True, "team": copy.deepcopy(team)}
        return self.state.mutate(mutate)

    def status(self):
        return self.state.load()

    def open(self, now=None):
        now = datetime.fromtimestamp(now or time.time())
        def mutate(data):
            if data.get("status") == "running":
                return {"ok": False, "error": "الدوري مفتوح بالفعل.", "state": copy.deepcopy(data)}
            teams = list(data.get("teams", {}).values())
            if len(teams) < 2 or any(len(t.get("players", [])) != self.TEAM_SIZE for t in teams):
                return {"ok": False, "error": "يجب اكتمال فريقين على الأقل، وكل فريق أربعة لاعبين."}
            random.Random(str(now.date())).shuffle(teams)
            matches = []
            day = now.replace(hour=self.match_hour, minute=0, second=0, microsecond=0)
            if day <= now:
                day += timedelta(days=1)
            round_no, pairs = 1, teams
            while len(pairs) > 1:
                next_round = []
                for i in range(0, len(pairs), 2):
                    a, b = pairs[i], pairs[i + 1]
                    match = {"id": uuid.uuid4().hex, "round": round_no, "team1": a["name"], "team2": b["name"], "room1": a["room"], "room2": b["room"], "at": day.isoformat(), "status": "scheduled", "winner": "", "prize_per_player": self.QUALIFYING_PRIZE, "final_prize": 0}
                    matches.append(match)
                    next_round.append({"name": f"الفائز {match['id'][:6]}", "room": "", "players": []})
                    day += timedelta(days=1)
                if len(next_round) == 1:
                    break
                pairs = next_round
                round_no += 1
            if matches:
                matches[-1]["prize_per_player"] = 0
                matches[-1]["final_prize"] = self.FINAL_PRIZE
            data["status"], data["opened_at"], data["matches"] = "running", int(time.time()), matches
            return {"ok": True, "matches": copy.deepcopy(matches), "teams": len(teams)}
        return self.state.mutate(mutate)

    def summary(self):
        data = self.state.load()
        teams = list(data.get("teams", {}).values())
        lines = [f"🏏 دوري الكركيت: {len(teams)} فريقًا", f"الحالة: {data.get('status', 'registration')}"]
        for team in teams:
            lines.append(f"• {team.get('name')} — {team.get('room')} — {len(team.get('players', []))}/4")
        for match in data.get("matches", []):
            lines.append(f"📅 الجولة {match.get('round')}: {match.get('team1')} × {match.get('team2')} — {match.get('at')}")
        return "\n".join(lines)
