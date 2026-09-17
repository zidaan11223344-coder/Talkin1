import json
from pathlib import Path
import bot


def test_levels_stars_top10_and_welcome(tmp_path, monkeypatch):
    stats_file = tmp_path / "game_stats.json"
    monkeypatch.setattr(bot, "GAME_STATS_FILE", stats_file)
    stats = {}
    for i in range(1, 11):
        plays = 2000 if i == 1 else max(1, 100 - i)
        stats[f"user{i}"] = {
            "username": f"user{i}",
            "games": {"test": {"plays": plays, "points": plays, "staked": 0}},
        }
    stats["vip"] = {"username": "vip", "games": {}}
    stats_file.write_text(json.dumps(stats), encoding="utf-8")

    assert bot._game_level_info("user1")[0] == 7
    assert bot._game_star_rank("user1") == 1
    assert bot._game_star_rank("user7") == 7
    assert bot._game_star_rank("user8") is None
    assert len(bot._game_top10()) == 10
    assert "مستوى الألعاب: 7" in bot._game_welcome("user1", "room")
    assert "★★★★★★★" in bot._game_welcome("user1", "room")


def test_vip_keeps_original_welcome_at_level_one(tmp_path, monkeypatch):
    stats_file = tmp_path / "game_stats.json"
    monkeypatch.setattr(bot, "GAME_STATS_FILE", stats_file)
    stats_file.write_text(json.dumps({"vip": {"username": "vip", "games": {}}}), encoding="utf-8")
    assert bot._game_level_info("vip")[0] == 1
    assert bot._game_welcome("vip", "room").startswith("🎮 أهلاً")

print("game levels: PASS")
