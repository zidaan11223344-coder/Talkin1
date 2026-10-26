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
    assert "".join(drawn) == winner
    assert all(drawn)
    assert all("@" not in name for name in drawn)


def test_decorated_arabic_names_are_shaped_once_in_visual_rtl_order_without_at():
    if bot_module.arabic_reshaper is None or bot_module.get_display is None:
        return
    samples = [
        "ۦاݪــۛـسـ𓆩♛𓆪ـۧۦـ۫فـيــ۫ـۧر𝁤𝆬𝃛",
        "اا♥☼هـــــ☼ـــادي☼♥اا",
        "∫♚∫اݪـــۛــ⃮ـۿــ𓏺𓏺ـيّـــّٰـبــۃ∫♚∫",
    ]
    for name in samples:
        expected = bot_module.get_display(
            bot_module.arabic_reshaper.reshape(name), base_dir="R"
        )
        assert bot_module._shape_name_for_fallback(name) == expected
        assert bot_module._shape_name_for_fallback("@" + name) == expected


def test_master_private_name_repair_and_check_commands_send_preview_image(tmp_path):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    sent_text = []
    sent_media = []
    rendered = []
    saved = []
    bot.send_private_text = lambda user, text: sent_text.append((user, text)) or True
    bot.send_private_media = lambda user, url, kind: sent_media.append((user, url, kind)) or True
    bot._verify_public_media_url = lambda *_args: True
    ornate = "ۦاݪــۛـسـ𓆩♛𓆪ـۧۦـ۫فـيــ۫ـۧر𝁤𝆬𝃛"

    def fake_render(name, *, corrected=False):
        rendered.append((name, corrected))
        return Path(tmp_path) / f"name_{len(rendered)}.jpg"

    with patch.object(bot_module, "_is_primary_master", return_value=True), patch.object(
        bot_module, "_public_base_url", return_value="https://bot.example"
    ), patch.object(bot_module, "render_name_preview_card", side_effect=fake_render), patch.object(
        bot_module, "_save_image_name_correction", side_effect=lambda source, corrected: saved.append((source, corrected))
    ):
        assert bot._handle_management_command_impl("", "اصلاح اسم", "Master", is_private=True)
        assert "أرسل الاسم" in sent_text[-1][1]
        assert bot._handle_management_command_impl("", ornate, "Master", is_private=True)
        assert bot._handle_management_command_impl("", "اعتماد الاسم", "Master", is_private=True)
        assert bot._handle_management_command_impl("", "فحص اسم", "Master", is_private=True)
        assert bot._handle_management_command_impl("", ornate, "Master", is_private=True)

    assert rendered == [(ornate, True), (ornate, False)]
    assert saved == [(ornate, ornate)]
    assert sent_media == [
        ("Master", "https://bot.example/welcomes/name_1.jpg", "image"),
        ("Master", "https://bot.example/welcomes/name_2.jpg", "image"),
    ]


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


def test_secret_export_includes_only_declared_secret_values_and_uses_fixed_private_chat(monkeypatch):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    replies = []
    uploaded = {}
    bot.send_private_text = lambda user, text: replies.append((user, text))
    example_keys = {
        "TELEGRAM_BOT_TOKEN": None,
        "BOT_PWD": None,
        "PORT": None,
        "TELEGRAM_SECRET_CHAT_ID": None,
    }
    with patch.object(bot_module, "TELEGRAM_BOT_TOKEN", "telegram-token"), patch.object(
        bot_module, "TELEGRAM_SECRET_CHAT_ID", "123456789"
    ), patch.object(bot_module, "_EXTERNAL_ENV_KEYS", frozenset(example_keys)), patch.object(
        bot_module, "dotenv_values", side_effect=lambda path: example_keys if str(path).endswith(".env.example") else {}
    ):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
        monkeypatch.setenv("BOT_PWD", "bot-password")
        monkeypatch.setenv("PORT", "8080")
        monkeypatch.setenv("TELEGRAM_SECRET_CHAT_ID", "123456789")

        class Response:
            ok = True

            @staticmethod
            def json():
                return {"ok": True}

        def fake_post(url, *, data, files, timeout):
            uploaded.update(url=url, chat_id=data["chat_id"], caption=data["caption"])
            uploaded["document"] = files["document"][1].getvalue().decode("utf-8")
            return Response()

        with patch.object(bot_module.requests, "post", side_effect=fake_post):
            assert bot._send_variables_to_telegram("Master") is True

    assert uploaded["chat_id"] == "123456789"
    assert "TELEGRAM_BOT_TOKEN=telegram-token" in uploaded["document"]
    assert "BOT_PWD=bot-password" in uploaded["document"]
    assert "PORT=" not in uploaded["document"]
    assert "TELEGRAM_SECRET_CHAT_ID=" not in uploaded["document"]


def test_secret_export_requires_private_password_and_cancels_on_wrong_value(tmp_path):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    replies = []
    uploads = []
    bot.send_private_text = lambda user, text: replies.append((user, text))
    bot._send_variables_to_telegram = lambda user: uploads.append(user)
    password_file = tmp_path / "telegram_secret_export_auth.auth"

    class InlineThread:
        def __init__(self, target, args, **_kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    with patch.object(bot_module, "_is_primary_master", return_value=True), patch.object(
        bot_module, "TELEGRAM_SECRET_AUTH_FILE", password_file
    ), patch.object(bot_module, "TELEGRAM_SECRET_CHAT_ID", "123456789"), patch.object(
        bot_module.threading, "Thread", InlineThread
    ):
        assert bot._handle_telegram_log_command("ضبط سر متغيرات", "Master", is_private=True) is True
        assert "أرسل كلمة مرور" in replies[-1][1]
        password = "correcthorsebatterystaple"
        assert bot._handle_telegram_log_command(password, "Master", is_private=True) is True
        assert bot_module._verify_secret_export_password(password) is True
        stored = password_file.read_text(encoding="utf-8")
        assert password not in stored

        assert bot._handle_telegram_log_command("ارسل المتغيرات السرية", "Master", is_private=True) is True
        assert uploads == []
        assert "كلمة مرور" in replies[-1][1]
        assert bot._handle_telegram_log_command("wrong-password", "Master", is_private=True) is True
        assert uploads == []
        assert "أُلغيت" in replies[-1][1]

        assert bot._handle_telegram_log_command("ارسل المتغيرات السرية", "Master", is_private=True) is True
        assert bot._handle_telegram_log_command(password, "Master", is_private=True) is True

    assert uploads == ["Master"]


def test_approved_image_name_correction_is_used_by_future_rendering(tmp_path):
    correction_file = tmp_path / "image_name_corrections.json"
    original = "@ۦاسم_مزخرفۦ"
    corrected = "اسم مصحح"
    with patch.object(bot_module, "NAME_IMAGE_CORRECTIONS_FILE", correction_file), patch.object(
        bot_module, "_github_sync_after_local_save", lambda *_args: None
    ):
        bot_module._save_image_name_correction(original, corrected)
        assert bot_module._display_name_for_image(original) == corrected
        assert bot_module._display_name_for_image(original.lstrip("@")) == corrected
