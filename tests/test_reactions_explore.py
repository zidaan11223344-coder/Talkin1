from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
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


def test_explore_reaction_message_does_not_duplicate_post_text(monkeypatch, tmp_path):
    instance = _bare_bot()
    room_messages = []
    media_messages = []
    private_messages = []
    rendered = []
    avatar_url = "https://avatar.example/profile.jpg"
    instance.user_photos[bot_module._norm_user("ناشر")] = avatar_url
    instance._find_publish_filter_hit = lambda _text: False
    instance._lookup_profile_photo = lambda _sender: ""
    instance._active_rooms = lambda: ["غرفة"]
    instance._verify_public_media_url = lambda *_args: True
    instance.send_room_text = lambda room, text: room_messages.append((room, text)) or True
    instance.send_room_media = lambda room, url, kind: media_messages.append((room, url, kind)) or True
    instance.send_private_text = lambda user, text: private_messages.append((user, text)) or True
    monkeypatch.setattr(
        bot_module, "render_explore_card",
        lambda *args: rendered.append(args) or tmp_path / "card.jpg",
    )
    monkeypatch.setattr(bot_module, "_public_base_url", lambda: "https://media.example")

    assert instance._handle_explore_command("غرفة", "ax@نص المنشور يبقى داخل الصورة فقط", "ناشر")

    assert rendered[0][2] == avatar_url
    assert media_messages and media_messages[0][2] == "image"
    assert len(room_messages) == 1
    caption = room_messages[0][1]
    assert "نص المنشور يبقى داخل الصورة فقط" not in caption
    assert "📝" not in caption
    assert "lk@" in caption and "lv@" in caption and "dl@" in caption and "x@" in caption
    assert next(iter(instance.reaction_targets.values()))["description"] == "نص المنشور يبقى داخل الصورة فقط"


def test_explore_card_embeds_profile_photo_in_smaller_top_heart(tmp_path, monkeypatch):
    if not bot_module.PIL_AVAILABLE:
        return
    avatar = bot_module.Image.new("RGB", (240, 180), (220, 42, 112))
    buffer = BytesIO()
    avatar.save(buffer, format="PNG")
    response = SimpleNamespace(status_code=200, content=buffer.getvalue())
    monkeypatch.setattr(bot_module.requests, "get", lambda *_args, **_kwargs: response)
    with patch.object(bot_module, "BASE_DIR", Path(tmp_path)):
        card = bot_module.render_explore_card(
            "رسالة اكسبلور", "مستخدم", "https://avatar.example/profile.png"
        )
    try:
        with bot_module.Image.open(card) as image:
            assert image.size == (1080, 1500)
            assert image.format == "JPEG"
            # The avatar's magenta pixels must be visible in the heart at the top.
            red, green, blue = image.getpixel((540, 300))
            assert red > 160 and green < 100 and blue > 65
    finally:
        card.unlink(missing_ok=True)


def test_explore_username_supports_arabic_emoji_ornaments_and_gradient(monkeypatch):
    if not bot_module.PIL_AVAILABLE:
        return
    background = (17, 26, 58)
    image = bot_module.Image.new("RGB", (1080, 1500), background)
    rtl_runs = []
    original_text = bot_module.ImageDraw.ImageDraw.text

    def record_rtl_run(draw, xy, text, *args, **kwargs):
        if kwargs.get("direction") == "rtl":
            rtl_runs.append(text)
        return original_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(bot_module.ImageDraw.ImageDraw, "text", record_rtl_run)
    bot_module._draw_explore_username(
        bot_module.ImageDraw.Draw(image, "RGBA"),
        (540, 750),
        "@༺✨نـورا 🚀 𓆩♛𓆪༻",
        920,
    )
    pixel_bytes = image.crop((70, 710, 1010, 790)).tobytes()
    colors = {
        tuple(pixel_bytes[offset:offset + 3])
        for offset in range(0, len(pixel_bytes), 3)
        if tuple(pixel_bytes[offset:offset + 3]) != background
    }
    assert len(colors) > 20
    assert any(red > 220 and green > 110 and blue < 200 for red, green, blue in colors)
    assert any(red < 220 and green > 120 and blue > 180 for red, green, blue in colors)
    assert "نـورا" in rtl_runs


def test_mixed_explore_name_aligns_arabic_and_emoji_on_one_line(monkeypatch):
    text_centers = []
    emoji_centers = []

    def capture_text(_draw, xy, *_args, **kwargs):
        text_centers.append(kwargs.get("vertical_center"))
        return xy[0] + 20

    monkeypatch.setattr(
        bot_module, "_draw_name_visual", capture_text,
    )

    def capture_emoji(_draw, xy, _token, size):
        emoji_centers.append(xy[1] + size / 2)
        return size

    monkeypatch.setattr(bot_module, "_draw_color_emoji", capture_emoji)
    image = bot_module.Image.new("RGBA", (1080, 200), (0, 0, 0, 0))
    bot_module._draw_name_centered(
        bot_module.ImageDraw.Draw(image), (540, 100), "༺نورا🚀༻", 50,
        (255, 255, 255, 255), 900, grow_short=False,
        native_arabic_runs=True,
    )

    assert text_centers and all(center == 100 for center in text_centers)
    assert emoji_centers and all(abs(center - 100) <= 5 for center in emoji_centers)


def test_explore_mixed_name_draws_arabic_run_in_logical_rtl_order(monkeypatch):
    rtl_runs = []
    original_text = bot_module.ImageDraw.ImageDraw.text

    def record_rtl_run(draw, xy, text, *args, **kwargs):
        if kwargs.get("direction") == "rtl":
            rtl_runs.append(text)
        return original_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(bot_module.ImageDraw.ImageDraw, "text", record_rtl_run)
    image = bot_module.Image.new("RGBA", (1080, 200), (0, 0, 0, 0))
    bot_module._draw_name_centered(
        bot_module.ImageDraw.Draw(image), (540, 100), "༺نـورا🚀༻", 50,
        (255, 255, 255, 255), 900, grow_short=False,
        native_arabic_runs=True,
    )

    assert "نـورا" in rtl_runs


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


def test_explore_card_renders_full_face_and_compound_emoji_sequences(tmp_path, monkeypatch):
    if not bot_module.PIL_AVAILABLE:
        return
    rendered_emoji = []
    monkeypatch.setattr(
        bot_module, "_draw_color_emoji",
        lambda _draw, _xy, token, size: rendered_emoji.append(token) or size,
    )
    with patch.object(bot_module, "BASE_DIR", Path(tmp_path)):
        card = bot_module.render_explore_card(
            "سلام 😀😃😄😁😆😅😂🤣☺ 👨‍👩‍👧‍👦 👍🏽 🇸🇦", "مستخدم", ""
        )
    try:
        assert card.is_file()
        assert set("😀😃😄😁😆😅😂🤣☺").issubset(set(rendered_emoji))
        assert "👨‍👩‍👧‍👦" in rendered_emoji
        assert "👍🏽" in rendered_emoji
        assert "🇸🇦" in rendered_emoji
    finally:
        card.unlink(missing_ok=True)


def test_explore_text_palette_changes_between_consecutive_renders():
    first = bot_module._next_explore_text_color()
    second = bot_module._next_explore_text_color()
    assert first != second


def test_oversized_text_is_split_into_safe_websocket_packets(monkeypatch):
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

    assert result is True
    assert len(websocket_messages) > 1
    assert all(len(packet) <= 1008 for packet in websocket_messages)
    chunks = [bot_module.as_text(bot_module.decode_message(packet)[5][0]) for packet in websocket_messages]
    assert "".join(chunks) == "ط" * 700
    assert telegram_messages == []
    assert private_messages == []
