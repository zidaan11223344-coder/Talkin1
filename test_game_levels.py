import json
from pathlib import Path
import bot


def test_levels_stars_top10_and_welcome(tmp_path, monkeypatch):
    stats_file = tmp_path / "game_stats.json"
    levels_file = tmp_path / "game_levels.json"
    monkeypatch.setattr(bot, "GAME_STATS_FILE", stats_file)
    monkeypatch.setattr(bot, "GAME_LEVELS_FILE", levels_file)
    stats = {}
    for i in range(1, 11):
        plays = 20000 if i == 1 else max(1, 100 - i)
        stats[f"user{i}"] = {
            "username": f"user{i}",
            "games": {"test": {"plays": plays, "points": plays, "staked": 0}},
        }
    stats["vip"] = {"username": "vip", "games": {}}
    stats_file.write_text(json.dumps(stats), encoding="utf-8")

    assert bot._game_level_info("user1")[0] == 10
    assert bot._game_star_rank("user1") == 1
    assert bot._game_star_rank("user7") == 7
    assert bot._game_star_rank("user10") == 10
    assert len(bot._game_top10()) == 10
    welcome = bot._game_welcome("user1", "room")
    assert "🎮 دخل @user1" in welcome
    assert "أسطورة الأساطير قيمة المستوى" in welcome
    assert "🏅 مستوى الألعاب: 10" in welcome
    assert "⭐ ترتيب النجوم\n       ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐" in welcome
    bot._save_game_levels_snapshot()
    snapshot = json.loads(levels_file.read_text(encoding="utf-8"))
    assert snapshot["players"]["user1"]["level"] == 10
    assert snapshot["players"]["user1"]["star_rank"] == 1


def test_vip_keeps_original_welcome_at_level_one(tmp_path, monkeypatch):
    stats_file = tmp_path / "game_stats.json"
    levels_file = tmp_path / "game_levels.json"
    monkeypatch.setattr(bot, "GAME_STATS_FILE", stats_file)
    monkeypatch.setattr(bot, "GAME_LEVELS_FILE", levels_file)
    stats_file.write_text(json.dumps({"vip": {"username": "vip", "games": {}}}), encoding="utf-8")
    assert bot._game_level_info("vip")[0] == 1
    assert bot._game_welcome("vip", "room").startswith("🎮 أهلاً")


def test_zero_rounds_have_no_room_welcome_and_twenty_are_new(tmp_path, monkeypatch):
    stats_file = tmp_path / "game_stats.json"
    monkeypatch.setattr(bot, "GAME_STATS_FILE", stats_file)
    stats_file.write_text(json.dumps({
        "zero": {"username": "zero", "games": {}},
        "twenty": {"username": "twenty", "games": {"test": {"plays": 20}}},
    }), encoding="utf-8")
    assert bot._game_level_info("twenty")[1] == "لاعب جديد"
    assert bot._game_level_info("twenty")[0] == 1
    assert bot._game_level_info("zero")[2] == 0

print("game levels: PASS")
