import io
import threading
from pathlib import Path
from unittest.mock import patch

import bot as bot_module
import shop


def test_member_can_buy_and_activate_text_and_image_welcome(tmp_path, monkeypatch):
    monkeypatch.setattr(shop, "SHOP_PATH", tmp_path / "shop.json")
    monkeypatch.setattr(bot_module, "_is_verified_user", lambda _username: True)
    monkeypatch.setattr(bot_module, "_resolve_points_account", lambda *_args: ("player", {"points": 100_000_000}))
    monkeypatch.setattr(bot_module, "_points_data", lambda: {})
    monkeypatch.setattr(bot_module, "_points_balance", lambda _account: 100_000_000)
    monkeypatch.setattr(bot_module, "_add_points", lambda *_args: None)
    monkeypatch.setattr(bot_module, "_stored_user_id", lambda *_args: "")
    monkeypatch.setattr(bot_module, "_stored_user_aliases", lambda *_args: ())
    monkeypatch.setattr(bot_module, "_github_sync_after_local_save", lambda *_args: None)

    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.custom_welcomes = {}
    bot.custom_welcome_enabled = False
    bot.custom_welcome_image_pending = {}
    bot._master_reply_local = threading.local()
    replies = []
    bot.send_private_text = lambda user, text: replies.append((user, text))
    bot.send_room_text = lambda *_args: None
    bot._save_social_features = lambda: None
    bot._remember_bot_action = lambda *_args, **_kwargs: None

    # Buy the text welcome using the English purchase alias, then activate it.
    assert bot._handle_management_command("", "buy 5", "Player", is_private=True) is True
    assert shop.active("custom_welcome", username="Player")
    assert "أرسل نص الترحيب الآن" in replies[-1][1]
    assert bot._handle_management_command("", "أهلًا {username}", "Player", is_private=True) is True
    assert bot.custom_welcomes[bot_module._norm_user("Player")]["message"] == "أهلًا {username}"

    # Buy the image welcome using Arabic numerals; the upload request is immediate.
    assert bot._handle_management_command("", "شراء ٦", "Player", is_private=True) is True
    assert shop.active("image_welcome", username="Player")
    assert "أرسل صورة الترحيب الآن" in replies[-1][1]
    assert bot.custom_welcome_image_pending[bot_module._norm_user("Player")]["username"] == "Player"
    image_url = "https://cdn.example.test/welcome.jpg"
    assert bot._try_custom_welcome_image_media("Hall", image_url, ["Player"]) is True
    assert bot.custom_welcomes[bot_module._norm_user("Player")]["image_url"] == image_url
    assert bot_module._norm_user("Player") not in bot.custom_welcome_image_pending
    sent_images = []
    bot.send_room_media = lambda room, url, media_type: sent_images.append((room, url, media_type)) or True
    saved_welcome = bot.custom_welcomes[bot_module._norm_user("Player")]
    assert bot._send_saved_custom_welcome_image("Hall", "Player", saved_welcome, fresh_join=False) is False

    image_buffer = io.BytesIO()
    bot_module.Image.new("RGB", (320, 180), "navy").save(image_buffer, format="PNG")
    payload = image_buffer.getvalue()
    drawn_names = []

    class Response:
        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield payload

    class InlineThread:
        def __init__(self, target, args, **_kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    with patch.object(bot_module.threading, "Thread", InlineThread), patch.object(
        bot_module.requests, "get", return_value=Response()
    ), patch.object(bot_module, "BASE_DIR", Path(tmp_path)), patch.object(
        bot_module, "_public_base_url", return_value="https://bot.example"
    ), patch.object(bot, "_verify_public_media_url", return_value=True), patch.object(
        bot_module, "_draw_centered", lambda *_args, **_kwargs: None
    ), patch.object(
        bot_module, "_draw_name_centered", lambda _draw, _center, name, *_args, **_kwargs: drawn_names.append(name)
    ):
        assert bot._send_saved_custom_welcome_image("Hall", "Player", saved_welcome, fresh_join=True) is True

    assert len(sent_images) == 1 and sent_images[0][0] == "Hall" and sent_images[0][2] == "image"
    assert sent_images[0][1].startswith("https://bot.example/welcomes/welcome_")
    assert "Player" in drawn_names
    assert all("@" not in name for name in drawn_names)
