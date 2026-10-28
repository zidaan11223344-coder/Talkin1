from pathlib import Path
from unittest.mock import patch

import bot as bot_module


def test_gift_card_uses_rtl_name_rendering_only_for_sender_and_receiver(tmp_path):
    available = [
        (gift_id, path)
        for gift_id, paths in bot_module.GIFT_IMAGE_FILES.items()
        for path in paths
        if Path(path).is_file()
    ]
    assert available, "the test needs one original gift artwork asset"
    gift_id, _gift_path = available[0]
    sender = "༺نـورا🚀༻"
    receiver = "༺دانا🚀༻"
    rendered_names = []

    def capture_name(_draw, _center, name, *_args, **kwargs):
        rendered_names.append((name, kwargs.get("native_arabic_runs", False)))

    with patch.object(bot_module, "BASE_DIR", Path(tmp_path)), patch.object(
        bot_module, "_load_sender_avatar", return_value=None
    ), patch.object(
        bot_module, "_draw_centered", lambda *_args, **_kwargs: None
    ), patch.object(bot_module, "_draw_name_centered", capture_name):
        card = bot_module.render_gift_card(gift_id, sender, receiver)

    assert card.is_file()
    assert rendered_names == [(sender, True), (receiver, True)]
