import threading
from pathlib import Path
from unittest.mock import patch

import bot as bot_module


def test_publish_unban_and_room_broadcast_are_recognized_as_commands():
    assert bot_module._looks_like_bot_command("mbp@SomeUser")
    assert bot_module._looks_like_bot_command("رساله غرفه@تنبيه")
    assert bot_module._looks_like_admin_command("mbp@SomeUser")


def test_publish_ban_removal_removes_matching_rows_for_decorated_name(tmp_path):
    path = tmp_path / "publish_bans.json"
    ornate = "∫♚∫اݪـــۛــ⃮ـۿــ𓏺𓏺ـيّـــّٰـبــۃ∫♚∫"
    with patch.object(bot_module, "PUBLISH_BANS_FILE", path):
        bot_module._record_publish_ban(ornate, "Hall", "blocked word")
        assert bot_module._is_publish_banned(ornate)
        removed = bot_module._remove_publish_ban("@" + ornate)
        assert removed == 1
        assert not bot_module._is_publish_banned(ornate)


def test_room_broadcast_runs_on_dedicated_queue_worker():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._room_broadcast_queue = __import__("queue").Queue(maxsize=2)
    bot._room_bulk_lock = threading.Lock()
    delivered = []
    completed = threading.Event()
    reports = []
    bot._active_rooms = lambda: ["Room A", "Room B"]
    bot.send_room_text = lambda room, text: delivered.append((room, text)) or (room == "Room A")
    bot.send_private_text = lambda user, text: (reports.append((user, text)), completed.set())
    bot.log = lambda *_args: None
    worker = threading.Thread(target=bot._room_broadcast_worker_loop, daemon=True)
    worker.start()

    assert bot._queue_room_broadcast("رسالة اختبار", "Master") is True
    assert completed.wait(2.0)
    assert delivered == [("Room A", "رسالة اختبار"), ("Room B", "رسالة اختبار")]
    assert "وصلت إلى 1 غرفة، وفشل 1 من 2" in reports[-1][1]
    assert bot._room_broadcast_queue.unfinished_tasks == 0


def test_long_decorated_winner_name_is_rendered_on_two_readable_lines(tmp_path):
    if not bot_module.PIL_AVAILABLE:
        return
    winner = "∫♚∫اݪـــۛــ⃮ـۿــ𓏺𓏺ـيّـــّٰـبــۃ∫♚∫"
    drawn = []
    with patch.object(bot_module, "BASE_DIR", Path(tmp_path)), patch.object(
        bot_module, "_load_sender_avatar", return_value=None
    ), patch.object(bot_module, "_draw_centered", lambda *_args, **_kwargs: None), patch.object(
        bot_module, "_draw_name_centered",
        lambda _draw, _center, text, *_args, **_kwargs: drawn.append(text),
    ):
        card = bot_module.render_money_game_winner_card("million", winner)
    assert card.is_file()
    assert len(drawn) == 2
    assert "".join(drawn).lstrip("@") == winner


def test_master_can_post_personalized_million_and_billion_preview_to_command_room(tmp_path):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.stock_pending = {}
    bot._pending_bomb_targets = {}
    bot._handle_pending_bot_choice = lambda *_args: False
    bot._snake_command = lambda *_args: False
    bot._ludo_command = lambda *_args: False
    bot.send_room_text = lambda *_args: True
    sent_media = []
    bot.send_room_media = lambda room, url, media_type: sent_media.append((room, url, media_type)) or True
    bot.send_private_text = lambda *_args: True
    bot._verify_public_media_url = lambda *_args: True
    rendered = []

    def fake_render(game_key, winner_name):
        rendered.append((game_key, winner_name))
        return Path(tmp_path) / f"{game_key}_winner.jpg"

    with patch.object(bot_module, "_is_primary_master", return_value=True), patch.object(
        bot_module, "BOT_MASTER", "ConfiguredMaster"
    ), patch.object(bot_module, "_public_base_url", return_value="https://bot.example"), patch.object(
        bot_module, "PIL_AVAILABLE", True
    ), patch.object(bot_module, "render_money_game_winner_card", side_effect=fake_render):
        assert bot.handle_game_command("Room A", "فحص صورة المليون", "ConfiguredMaster") is True
        assert bot.handle_game_command("Room B", "فحص صورة المليار", "ConfiguredMaster") is True

    assert rendered == [("million", "ConfiguredMaster"), ("billion", "ConfiguredMaster")]
    assert sent_media == [
        ("Room A", "https://bot.example/games/million_winner.jpg", "image"),
        ("Room B", "https://bot.example/games/billion_winner.jpg", "image"),
    ]
