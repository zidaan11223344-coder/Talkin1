import json
from unittest.mock import patch

import bot as bot_module


def _points_file(monkeypatch, tmp_path, accounts):
    points_path = tmp_path / "points.json"
    points_path.write_text(json.dumps(accounts, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(bot_module, "POINTS_FILE", points_path)
    monkeypatch.setattr(bot_module, "_STATE_DB_ENABLED", False)
    monkeypatch.setattr(bot_module, "_STATE_DB", None)
    monkeypatch.setattr(bot_module, "_POINTS_CACHE", None)
    monkeypatch.setattr(bot_module, "_POINTS_TRANSFER_CACHE", None)
    return points_path


def _bare_bot():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._send_text_packets = lambda *args, **kwargs: True
    bot.send_private_text = lambda *_args, **_kwargs: True
    bot.send_room_text = lambda *_args, **_kwargs: True
    return bot


def test_ts_replaces_existing_balance_and_records_audit(monkeypatch, tmp_path):
    path = _points_file(monkeypatch, tmp_path, {"player": {"username": "Player", "points": 750}})
    bot = _bare_bot()
    replies = []
    bot.send_private_text = lambda user, text: replies.append((user, text)) or True

    with patch.object(bot_module, "BOT_MASTER", "Master"):
        assert bot._handle_management_command_impl("", "ts@Player@1250", "Master", is_private=True)

    saved = json.loads(path.read_text(encoding="utf-8"))
    accounts, history = bot_module._decode_points_payload(saved)
    assert accounts["player"]["points"] == 1250
    assert len(history) == 1
    assert history[0]["old_balance"] == 750
    assert history[0]["new_balance"] == 1250
    assert history[0]["actor"] == "Master"
    assert "قبل: 750" in replies[0][1] and "بعد: 1,250" in replies[0][1]


def test_ts_can_set_zero_but_does_not_create_unknown_account(monkeypatch, tmp_path):
    path = _points_file(monkeypatch, tmp_path, {"player": {"username": "Player", "points": 10}})
    bot = _bare_bot()
    replies = []
    bot.send_private_text = lambda user, text: replies.append(text) or True

    with patch.object(bot_module, "BOT_MASTER", "Master"):
        assert bot._handle_management_command_impl("", "ts@Player@0", "Master", is_private=True)
        assert bot._handle_management_command_impl("", "ts@Missing@200", "Master", is_private=True)

    accounts, history = bot_module._decode_points_payload(json.loads(path.read_text(encoding="utf-8")))
    assert accounts == {"player": {"username": "Player", "points": 0}}
    assert len(history) == 1
    assert "لم أجد @Missing" in replies[-1]


def test_ts_refuses_ambiguous_duplicate_username(monkeypatch, tmp_path):
    path = _points_file(monkeypatch, tmp_path, {
        "player-a": {"username": "Player", "points": 10},
        "player-b": {"username": "Player", "points": 20},
    })
    bot = _bare_bot()
    replies = []
    bot.send_private_text = lambda _user, text: replies.append(text) or True

    with patch.object(bot_module, "BOT_MASTER", "Master"):
        assert bot._handle_management_command_impl("", "ts@Player@100", "Master", is_private=True)

    accounts, history = bot_module._decode_points_payload(json.loads(path.read_text(encoding="utf-8")))
    assert accounts["player-a"]["points"] == 10
    assert accounts["player-b"]["points"] == 20
    assert history == []
    assert "أكثر من سجل مطابق" in replies[0]


def test_ts_rejects_non_master_and_room_usage(monkeypatch, tmp_path):
    path = _points_file(monkeypatch, tmp_path, {"player": {"username": "Player", "points": 10}})
    bot = _bare_bot()
    replies = []
    bot.send_private_text = lambda _user, text: replies.append(text) or True
    bot.send_room_text = lambda _room, text: replies.append(text) or True

    with patch.object(bot_module, "BOT_MASTER", "Master"):
        assert bot._handle_management_command_impl("", "ts@Player@20", "Other", is_private=True)
        assert bot._handle_management_command_impl("Hall", "ts@Player@20", "Master", is_private=False)

    accounts, history = bot_module._decode_points_payload(json.loads(path.read_text(encoding="utf-8")))
    assert accounts["player"]["points"] == 10
    assert history == []
    assert any("مخصص للماستر الأساسي" in reply for reply in replies)
    assert any("خاص البوت" in reply for reply in replies)


def test_ts_is_recognized_as_admin_command():
    assert bot_module._looks_like_admin_command("ts@Player@300")
    assert bot_module._looks_like_bot_command("ts@Player@300")


def test_a1_sections_are_numbered_and_include_next_navigation():
    sections = bot_module._default_help_sections()[1]
    assert len(sections) == 9
    for number, section in enumerate(sections, start=1):
        assert f"الإدارة — {number} |" in section
    assert "k@اسم — طرد عضو" in sections[0]
    assert "m@اسم — منح عضوية" in sections[1]
    assert "ts@اسم@عدد" in sections[6]
    assert "l@all" in sections[7]
    bot = _bare_bot()
    sent = []
    bot._send_help_chunks = lambda _packet, text, **_kwargs: sent.append(text) or True
    bot._send_help_section(private_to="Master", page=1, part=1)
    assert "📌 للقائمة التالية اكتب ns" in sent[0]


def test_ns_after_a1_advances_before_stale_generic_results(monkeypatch):
    bot = _bare_bot()
    bot.help_pages = {}
    bot.help_page_part = {}
    bot.help_game_part = {}
    bot._filter_list_state = {}
    bot._filter_list_key = lambda *_args: "filter-key"
    bot._transfer_log_pages = {}
    bot._transfer_log_targets = {}
    bot._transfer_log_languages = {}
    bot._result_pages = {
        ("chat_message", "", "Master"): {"pages": ["stale result 1", "stale result 2"], "part": 1}
    }
    sent = []
    private_sent = []
    bot._send_help = lambda **kwargs: sent.append(kwargs) or True
    bot.send_private_text = lambda _user, text: private_sent.append(text) or True

    with patch.object(bot_module, "_is_primary_master", return_value=True):
        assert bot._handle_management_command("", "a1", "Master", is_private=True)
        for expected_page in range(2, 10):
            assert bot._handle_management_command("", "ns", "Master", is_private=True)
            key = ("__private__", bot_module._norm_user("Master"))
            assert bot.help_page_part[key] == expected_page
        assert bot._handle_management_command("", "ns", "Master", is_private=True)

    key = (("__private__"), bot_module._norm_user("Master"))
    assert bot.help_pages[key] == 1
    assert bot.help_page_part[key] == 9
    assert sent[-1]["page"] == 1 and sent[-1]["game_part"] == 9
    assert "انتهت قوائم الإدارة" in private_sent[-1]
    assert bot._result_pages[("chat_message", "", "Master")]["part"] == 1
