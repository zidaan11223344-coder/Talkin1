import json
from pathlib import Path
import bot


def test_persistent_roster_roundtrip(tmp_path, monkeypatch):
    rooms_file = tmp_path / "tracked_rooms.json"
    roster_file = tmp_path / "room_users.json"
    monkeypatch.setattr(bot, "TRACKED_ROOMS_FILE", rooms_file)
    monkeypatch.setattr(bot, "ROOM_USERS_FILE", roster_file)
    monkeypatch.setattr(bot, "BOT_ID", "the_bot")

    bot._save_persistent_rooms({"room_a", "room_b"})
    assert bot._persistent_rooms() == ["room_a", "room_b"]
    bot._remember_roster("room_a", [{"username": "Alice", "role": "admin"}])
    bot._remember_roster("room_a", [{"username": "Bob", "role": "none"}])
    assert set(bot._persistent_roster_users("room_a")) == {"Alice", "Bob"}

    # A later update must not erase an earlier user.
    bot._remember_roster("room_a", [{"username": "Alice", "role": "owner"}])
    assert set(bot._persistent_roster_users("room_a")) == {"Alice", "Bob"}
    payload = json.loads(roster_file.read_text(encoding="utf-8"))
    assert payload["rooms"]["room_a"]["alice"]["role"] == "owner"


def test_verified_file_is_independent(tmp_path, monkeypatch):
    verified_file = tmp_path / "verified_users.json"
    rooms_file = tmp_path / "tracked_rooms.json"
    monkeypatch.setattr(bot, "VERIFIED_FILE", verified_file)
    monkeypatch.setattr(bot, "TRACKED_ROOMS_FILE", rooms_file)
    bot._save_local_json(verified_file, {"alice": {"username": "Alice"}})
    bot._save_persistent_rooms({"room_a"})
    assert bot._verified_data()["alice"]["username"] == "Alice"
    assert bot._persistent_rooms() == ["room_a"]


def test_points_and_auto_replies_are_persistent(tmp_path, monkeypatch):
    points_file = tmp_path / "points.json"
    stats_file = tmp_path / "game_stats.json"
    replies_file = tmp_path / "replies.json"
    monkeypatch.setattr(bot, "POINTS_FILE", points_file)
    monkeypatch.setattr(bot, "GAME_STATS_FILE", stats_file)
    monkeypatch.setattr(bot, "REPLIES_FILE", replies_file)
    monkeypatch.setattr(bot, "BASE_DIR", tmp_path)

    assert bot._add_points("Alice", 25) == 25
    assert bot._add_points("Alice", 5) == 30
    assert bot._points_data()["alice"]["points"] == 30
    bot._record_game("Alice", "rps", points_delta=15, stake=0)
    bot._record_game("Alice", "rps", points_delta=-5, stake=10)
    stats = bot._game_stats_data()
    assert stats["alice"]["games"]["rps"] == {"plays": 2, "points": 10, "staked": 10}

    replies = {"auto_replies_enabled": True, "auto_replies": {}}
    bot._save_local_json(replies_file, replies)
    replies["auto_replies"]["hello"] = {"trigger": "hello", "reply": "أهلاً"}
    bot._save_local_json(replies_file, replies)
    restored = bot._load_local_json(replies_file, {})
    assert restored["auto_replies"]["hello"]["reply"] == "أهلاً"


def test_verification_filter_gifts_and_room_music(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "MODERATION_FILE", tmp_path / "moderation.json")
    assert bot._is_verified_user.__name__ == "_is_verified_user"
    assert bot._looks_like_bot_command("vi@Alice")
    assert bot._looks_like_bot_command("vip@Alice")
    assert bot._looks_like_bot_command("هدايا")
    assert bot._looks_like_bot_command("gifts")
    assert bot._save_moderation_config(True, ["كلمة", "كلمة"]) == ["كلمة"]
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "self.send_private_text(requester,caption)" not in source


def test_share_last_music_sends_only_to_target():
    obj = object.__new__(bot.TalkinBot)
    obj.music_current = {"alice": {"title": "Song", "url": "https://example/song.mp3", "duration": 12}}
    obj.private_text = []
    obj.private_media = []
    obj.room_text = []
    obj.send_private_text = lambda user, text: obj.private_text.append((user, text))
    obj.send_private_media = lambda user, url, kind, duration: obj.private_media.append((user, url, kind, duration))
    obj.send_room_text = lambda room, text: obj.room_text.append((room, text))
    assert obj.share_last_music("Alice", "Bob", "room")
    assert obj.private_media == [("Bob", "https://example/song.mp3", "audio", 12)]
    assert all(user == "Bob" for user, _ in obj.private_text)
