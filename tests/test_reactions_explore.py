from pathlib import Path
from unittest.mock import patch

import bot as bot_module


def _bare_bot():
    instance = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    instance.reaction_targets = {}
    instance.user_photos = {}
    return instance


def test_like_acknowledges_room_and_keeps_publisher_private_notice():
    instance = _bare_bot()
    room_messages = []
    private_messages = []
    instance.send_room_text = lambda room, text: room_messages.append((room, text)) or True
    instance.send_private_text = lambda user, text: private_messages.append((user, text)) or True
    instance.reaction_targets["a1b2"] = {
        "publisher": "post_owner", "kind": "explore", "description": "نص تجريبي", "created_at": bot_module.time.time()
    }

    assert instance._handle_reaction_command("غرفة", "lk@a1b2", "فاعل")
    assert "لقد اعجبت بمنشور" in room_messages[0][1]
    assert private_messages[0][0] == "post_owner"
    assert "إعجاب" in private_messages[0][1]


def test_report_acknowledges_room_and_notifies_master(monkeypatch):
    instance = _bare_bot()
    room_messages = []
    private_messages = []
    instance.send_room_text = lambda room, text: room_messages.append((room, text)) or True
    instance.send_private_text = lambda user, text: private_messages.append((user, text)) or True
    instance.reaction_targets["c3d4"] = {
        "publisher": "owner", "kind": "music", "title": "أغنية", "created_at": bot_module.time.time()
    }
    monkeypatch.setattr(bot_module, "BOT_MASTER", "master")

    assert instance._handle_reaction_command("غرفة", "report@c3d4 سبب البلاغ", "مبلّغ")
    assert "تم ارسال البلاغ" in room_messages[0][1]
    assert private_messages[0][0] == "master"
    assert "سبب البلاغ" in private_messages[0][1]


def test_x_reposts_explore_image_and_names_reposter():
    instance = _bare_bot()
    room_messages = []
    media_messages = []
    instance.send_room_text = lambda room, text: room_messages.append((room, text)) or True
    instance.send_room_media = lambda room, url, kind: media_messages.append((room, url, kind)) or True
    instance.reaction_targets["e5f6"] = {
        "kind": "explore", "media_url": "https://media.example/explore.jpg",
        "caption": "✨ اكسبلور\n👤 @author\n🔁 x@e5f6 — إعادة نشر",
        "created_at": bot_module.time.time(),
    }

    assert instance._handle_reaction_command("غرفة", "x@e5f6", "مُعيد")
    assert media_messages == [("غرفة", "https://media.example/explore.jpg", "image")]
    assert "أعاد النشر: @مُعيد" in room_messages[0][1]


def test_explore_card_is_created_as_a_fresh_image(tmp_path):
    if not bot_module.PIL_AVAILABLE:
        return
    with patch.object(bot_module, "BASE_DIR", Path(tmp_path)):
        card = bot_module.render_explore_card("رسالة اكسبلور", "مستخدم", "")
    try:
        assert card.is_file()
        with bot_module.Image.open(card) as image:
            assert image.size == (1080, 1500)
            assert image.format == "JPEG"
    finally:
        card.unlink(missing_ok=True)


def test_explore_username_uses_native_right_to_left_text(monkeypatch):
    drawn = []

    class DrawRecorder:
        def textbbox(self, _xy, text, **kwargs):
            assert text == "المستخدم العربي"
            assert kwargs.get("direction") == "rtl"
            return (0, 0, 240, 50)

        def text(self, _xy, text, **kwargs):
            drawn.append((text, kwargs))

    monkeypatch.setattr(bot_module, "_display_name_for_image", lambda value: value)
    monkeypatch.setattr(bot_module, "_gift_font", lambda *_args: object())
    monkeypatch.setattr(bot_module.features, "check", lambda _feature: True)

    bot_module._draw_explore_username(DrawRecorder(), (500, 500), "المستخدم العربي", 900)

    assert drawn[0][0] == "المستخدم العربي"
    assert drawn[0][1]["direction"] == "rtl"
    assert drawn[0][1]["language"] == "ar"


def test_explore_text_palette_changes_between_consecutive_renders():
    first = bot_module._next_explore_text_color()
    second = bot_module._next_explore_text_color()
    assert first != second


def test_oversized_text_is_forwarded_to_telegram_and_master_not_websocket(monkeypatch):
    instance = _bare_bot()
    telegram_messages = []
    private_messages = []
    websocket_messages = []
    instance._report_oversize_delivery = lambda *args: None
    instance._send_long_text_to_telegram = lambda text, title="": telegram_messages.append((text, title)) or True
    instance._send_oversize_notice = lambda *args, **kwargs: True
    instance.send_private_text = lambda user, text: private_messages.append((user, text)) or True
    instance.send_query = lambda payload: websocket_messages.append(payload) or True
    monkeypatch.setattr(bot_module, "BOT_MASTER", "master")

    result = instance._send_text_packets("room_message", "ط" * 700, room="غرفة")

    assert result is False
    assert telegram_messages and telegram_messages[0][0] == "ط" * 700
    assert "Telegram" in private_messages[0][1]
    assert websocket_messages == []
