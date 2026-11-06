import re
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import bot as bot_module


def test_unconfirmed_bot_user_left_keeps_room_presence_and_does_not_rejoin():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.connected_rooms = {"BlueBird"}
    bot._intentional_leaves = set()
    logs = []
    bot.log = lambda *args: logs.append(args)

    with patch.object(bot_module, "BOT_ID", "test-bot"):
        bot._handle_unconfirmed_bot_user_left("BlueBird")

    assert bot.connected_rooms == {"BlueBird"}
    assert any("USER_LEFT_IGNORED" in str(part) for row in logs for part in row)


def test_la_room_roster_requests_live_occupants_and_replies_in_public_or_private():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.ws = object()
    bot._pending_room_lists = {}
    queries = []
    private_messages = []
    public_results = []
    private_results = []
    bot.send_query = lambda query: queries.append(query)
    bot.send_private_text = lambda user, text: private_messages.append((user, text)) or True
    bot._extract_room_list_users = lambda _result: [
        {"username": "Alice"}, {"username": "alice"}, {"username": "test-bot"}, {"username": "Bob"}
    ]
    bot._send_room_list = lambda room, title, users, empty, sender="": public_results.append((room, title, users, sender))
    bot._send_private_list = lambda sender, title, users, empty: private_results.append((sender, title, users))

    with patch.object(bot_module, "BOT_ID", "test-bot"), patch.object(
        bot_module.member_shop, "active", return_value=False
    ):
        assert bot._room_list_commands("Source", "la@Hall", "Player", is_private=False)
        public_pending = bot._pending_room_lists[bot_module._norm_room("Hall")]
        assert public_pending["code"] == "la"
        assert public_pending["private_response"] is False
        assert public_pending["response_room"] == "Source"
        assert bot._complete_pending_room_list({"_occupants_room": "Hall"})

        assert bot._room_list_commands("Source", "la@Hall", "Player", is_private=True)
        private_pending = bot._pending_room_lists[bot_module._norm_room("Hall")]
        assert private_pending["private_response"] is True
        assert bot._complete_pending_room_list({"_occupants_room": "Hall"})

    assert len(queries) == 2
    assert len(public_results) == 1
    assert public_results[0][0] == "Source"
    assert [row["username"] for row in public_results[0][2]] == ["Alice", "Bob"]
    assert len(private_results) == 1
    assert [row["username"] for row in private_results[0][2]] == ["Alice", "Bob"]
    assert private_messages == []  # no noisy "fetching..." DM for a public command


def test_room_roster_pages_are_limited_to_thirty_and_reset_numbering():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._result_pages = {}
    sent = []
    bot.send_room_text = lambda room, text: sent.append((room, text)) or True
    users = [{"username": f"Member{i:02d}"} for i in range(65)]

    bot._send_room_list("Hall", "🟢 المتواجدون الآن في Hall", users, sender="Player")

    state = bot._result_pages[("room_message", "Hall", "Player")]
    assert len(state["pages"]) == 3
    row_counts = []
    for page in state["pages"]:
        numbers = [int(match.group(1)) for match in re.finditer(r"(?m)^(\d+)\. @", page)]
        row_counts.append(len(numbers))
        assert numbers == list(range(1, len(numbers) + 1))
    assert row_counts == [30, 30, 5]
    assert "للقائمة التالية اكتب Ns" in sent[0][1]


def test_la_text_roster_response_returns_list_in_command_room():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._pending_room_lists = {
        bot_module._norm_room("Target"): {
            "room": "Target", "code": "la", "sender": "Player",
            "request_type": "occupants_list", "response_room": "Source",
            "private_response": False,
        }
    }
    public = []
    private = []
    bot._send_room_list = lambda room, title, users, empty, sender="": public.append((room, title, users, sender))
    bot.send_private_text = lambda user, text: private.append((user, text)) or True
    bot.log = lambda *_args: None

    handled = bot._complete_pending_room_list_text(
        "Target", "User List: Members 1/1 (Total: 2):\n1. @Alice\n2. @Bob"
    )

    assert handled
    assert public[0][0] == "Source"
    assert "المتواجدون الآن في Target" in public[0][1]
    assert [item["username"] for item in public[0][2]] == ["Alice", "Bob"]
    assert bot._pending_room_lists == {}


def test_la_request_timeout_reports_missing_server_response_in_command_room():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._pending_room_lists = {
        bot_module._norm_room("Target"): {
            "room": "Target", "code": "la", "request_id": "req-1",
            "response_room": "Source", "private_response": False,
        }
    }
    sent = []
    bot.send_room_text = lambda room, text: sent.append((room, text)) or True

    assert bot._room_list_response_timeout(bot_module._norm_room("Target"), "req-1")
    assert sent[0][0] == "Source"
    assert "لم يصل رد المتواجدين" in sent[0][1]
    assert not bot._pending_room_lists


def test_ns_advances_room_gift_page_when_sender_identity_format_changes():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._result_pages = {
        ("room_message", "Hall", "@AhMeD"): {
            "pages": ["🎁 القائمة الأولى", "🎁 القائمة الثانية"],
            "part": 1, "kwargs": {"room": "Hall"},
        }
    }
    bot._filter_list_state = {}
    bot._filter_list_key = lambda room, sender: (room, sender)
    bot._transfer_log_pages = {}
    bot.help_pages = {}
    packets = []
    bot.send_query = lambda payload: packets.append(bytes(payload)) or True

    assert bot._handle_management_command("Hall", "ns", "ahmed", is_private=False)
    body = bot_module.as_text(bot_module.decode_message(packets[-1])[5][0])
    assert "🎁 القائمة الثانية" in body
    assert bot._result_pages[("room_message", "Hall", "@AhMeD")]["part"] == 2
    assert len(packets[-1]) < 1008


def test_report_reactions_are_delivered_only_to_master_private_chat():
    for kind in ("music", "image"):
        bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
        bot.reaction_targets = {
            "a1b2": {
                "publisher": "Publisher", "kind": kind, "title": "Track or photo",
                "created_at": time.time(),
            }
        }
        bot._master_reply_local = SimpleNamespace(rerouting=False)
        private, public, logs = [], [], []
        bot.send_private_text = lambda user, text: private.append((user, text)) or True
        bot.send_room_text = lambda room, text: public.append((room, text)) or True
        bot.log = lambda *args: logs.append(args)
        with patch.object(bot_module, "BOT_MASTER", "RoomMaster"):
            assert bot._handle_reaction_command("Hall", "report@a1b2 spam report", "Reporter")
        assert len(private) == 1
        assert private[0][0] == "RoomMaster"
        assert "Reporter" in private[0][1] and "a1b2" in private[0][1]
        assert public == []
        assert bot._master_reply_local.rerouting is False


def test_new_commands_are_classified_before_verification_gate():
    assert bot_module._looks_like_bot_command("la@Hall")
    assert bot_module._looks_like_bot_command("sby 1")
    assert bot_module._looks_like_bot_command("store")
    assert bot_module._looks_like_bot_command("متجر")
    assert bot_module._looks_like_bot_command("ايدي")
    assert bot_module._looks_like_bot_command("id@Ahmed")


def test_id_command_queries_server_and_returns_numeric_user_id():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.ws = object()
    bot._pending_room_lists = {}
    queries = []
    replies = []
    bot.send_query = lambda query: queries.append(query)
    bot.send_room_text = lambda room, text: replies.append((room, text))
    bot.send_private_text = lambda user, text: replies.append((user, text))
    bot._extract_room_list_users = lambda _result: [
        {"username": "Ahmed", "user_id": "3456782", "role": "member"}
    ]

    with patch.object(bot_module, "_stored_user_id", return_value=""), patch.object(
        bot_module, "_remember_roster"
    ):
        assert bot._room_list_commands("Hall", "ايدي@Ahmed", "Requester", is_private=False)
        pending = bot._pending_room_lists[bot_module._norm_room("Hall")]
        assert pending["code"] == "uid"
        assert pending["target"] == "Ahmed"
        assert pending["request_type"] == "members_list"
        assert bot._complete_pending_room_list({"_occupants_room": "Hall"})

    assert len(queries) == 1
    assert replies[-1][0] == "Hall"
    assert replies[-1][1] == "3456782"


def test_id_command_returns_cached_id_as_plain_number():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    replies = []
    bot.send_room_text = lambda room, text: replies.append((room, text))
    with patch.object(bot_module, "_stored_user_id", return_value="3456782"):
        assert bot._room_list_commands("Hall", "ايدي", "Ahmed", is_private=False)
    assert replies == [("Hall", "3456782")]


def test_id_command_is_routed_before_master_only_management_gate():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    calls = []
    bot._room_list_commands = lambda room, text, sender, is_private: calls.append(
        (room, text, sender, is_private)
    ) or True

    assert bot._handle_management_command("Hall", "ايدي", "RegularMember", is_private=False)
    assert calls == [("Hall", "ايدي", "RegularMember", False)]


def test_la_command_is_routed_before_master_only_management_gate():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    calls = []
    bot._room_list_commands = lambda room, text, sender, is_private: calls.append(
        (room, text, sender, is_private)
    ) or True

    assert bot._handle_management_command("Hall", "la@سوريانا", "RegularMember", is_private=False)
    assert calls == [("Hall", "la@سوريانا", "RegularMember", False)]


def test_shop_and_purchase_commands_pass_for_regular_members():
    import threading
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._room_list_commands = lambda *_args, **_kwargs: False
    bot._pending_named_commands = {}
    bot._pending_protection_number = {}
    bot._master_reply_local = threading.local()
    calls = []
    bot._handle_management_command_impl = lambda room, body, sender, is_private=False: calls.append(
        (room, body, sender, is_private)
    ) or True
    bot._remember_bot_action = lambda *_args, **_kwargs: None

    assert bot._handle_management_command("Hall", "store", "RegularMember", is_private=False)
    assert bot._handle_management_command("Hall", "sby 1", "RegularMember", is_private=False)
    assert [call[1] for call in calls] == ["store", "sby 1"]


def test_stored_user_id_looks_up_case_insensitively_across_rooms():
    with patch.object(bot_module, "_persistent_rosters", return_value={
        "version": 1,
        "rooms": {"hall": {"ahmed": {"username": "Ahmed", "user_id": "3456782"}}},
    }):
        assert bot_module._stored_user_id("@AHMED", "Hall") == "3456782"


def test_canonical_message_username_prefers_username_over_numeric_transport_id():
    assert bot_module._canonical_message_username("3456782", "Ahmed", "opaque-token") == "Ahmed"
    assert bot_module._canonical_message_username("3456782", "") == ""


def test_lightweight_room_command_uses_direct_event_path():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    calls = []
    bot.handle_room_event = lambda result: calls.append(result) or True
    result = {"room_event": {1: "text", 6: "ns", 13: "Hall"}}
    assert bot._dispatch_room_event(result) is True
    assert calls == [result]
    assert not hasattr(bot, "_room_command_executor")


def _install_fake_role_check_timers(monkeypatch):
    timers = []

    class FakeTimer:
        def __init__(self, interval, function, args=(), kwargs=None):
            self.interval = interval
            self.function = function
            self.args = args
            self.kwargs = kwargs or {}
            self.daemon = False
            self.cancelled = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(bot_module.threading, "Timer", FakeTimer)
    return timers


def test_rank_command_queries_server_and_reports_owner_in_same_room(monkeypatch):
    timers = _install_fake_role_check_timers(monkeypatch)
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.ws = object()
    bot._pending_room_lists = {}
    bot._pending_bot_room_role_checks = {}
    bot.bot_room_roles = {bot_module._norm_room("Hall"): "member"}
    queries, messages = [], []
    bot.send_query = lambda query: queries.append(query) or True
    bot.send_room_text = lambda room, text: messages.append((room, text)) or True
    bot.log = lambda *_args: None
    bot._extract_room_list_users = lambda _result: [{"username": "@TEST-BOT", "role": "owner"}]

    with patch.object(bot_module, "BOT_ID", "test-bot"):
        assert bot._route_room_game_input("Hall", "Player", "رتبتك") is True
        pending = bot._pending_room_lists[bot_module._norm_room("Hall")]
        assert pending["request_type"] == "occupants_list"
        assert pending["code"] == "bot_role"
        assert pending["bot_role_check"] is True
        assert len(queries) == 1 and timers[0].interval == 12.0
        query_fields = bot_module.decode_message(queries[0])
        assert bot_module.as_text(query_fields[1][0]) == "room_admin"
        assert bot_module.as_text(query_fields[2][0]) == "occupants_list"
        assert bot_module.as_text(query_fields[4][0]) == "username"
        assert bot_module.as_text(query_fields[6][0]) == "Hall"
        assert bot._complete_pending_room_list({"_occupants_room": "Hall", "users": [{}]})

    assert bot.bot_room_roles[bot_module._norm_room("Hall")] == "owner"
    assert any(room == "Hall" and "أونر (Owner)" in text and "الخادم" in text for room, text in messages)
    assert not bot._pending_room_lists
    assert not bot._pending_bot_room_role_checks
    assert timers[0].cancelled


def test_rank_command_sends_one_server_request_and_uses_only_the_bot_entry(monkeypatch):
    _install_fake_role_check_timers(monkeypatch)
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.ws = object()
    bot._pending_room_lists = {}
    bot._pending_bot_room_role_checks = {}
    bot.bot_room_roles = {}
    queries, messages = [], []
    bot.send_query = lambda query: queries.append(query) or True
    bot.send_room_text = lambda room, text: messages.append((room, text)) or True
    bot.log = lambda *_args: None
    bot._extract_room_list_users = lambda _result: [
        {"username": "OtherUser", "role": "owner"},
        {"username": "TalkinBot", "role": "member"},
    ]

    with patch.object(bot_module, "BOT_ID", "TalkinBot"):
        assert bot._handle_bot_room_role_command("BlueBird", "Player", "رتبتك")
        pending = bot._pending_room_lists[bot_module._norm_room("BlueBird")]
        assert pending["request_type"] == "occupants_list"
        assert bot._complete_pending_room_list({"_occupants_room": "BlueBird", "users": [{}]})

    assert len(queries) == 1
    assert bot.bot_room_roles[bot_module._norm_room("BlueBird")] == "member"
    assert any("عضو (Member)" in text for _room, text in messages)


def test_rank_command_falls_back_to_legacy_bot_target_after_app_timeout(monkeypatch):
    timers = _install_fake_role_check_timers(monkeypatch)
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.ws = object()
    bot._pending_room_lists = {}
    bot._pending_bot_room_role_checks = {}
    bot.bot_room_roles = {}
    queries, messages = [], []
    bot.send_query = lambda query: queries.append(query) or True
    bot.send_room_text = lambda room, text: messages.append((room, text)) or True
    bot.log = lambda *_args: None
    bot._extract_room_list_users = lambda _result: [
        {"username": "TalkinBot", "role": "owner"},
    ]

    with patch.object(bot_module, "BOT_ID", "TalkinBot"):
        assert bot._handle_bot_room_role_command("BlueBird", "Player", "رتبتك")
        room_key = bot_module._norm_room("BlueBird")
        first_request_id = bot._pending_bot_room_role_checks[room_key]["request_id"]
        first_fields = bot_module.decode_message(queries[0])
        assert bot_module.as_text(first_fields[4][0]) == "username"

        assert bot._bot_room_role_check_timeout(room_key, first_request_id)
        assert len(queries) == 2
        pending = bot._pending_room_lists[room_key]
        assert pending["request_mode"] == "legacy"
        assert len(timers) == 2 and timers[1].interval == 12.0
        fallback_fields = bot_module.decode_message(queries[1])
        assert bot_module.as_text(fallback_fields[4][0]) == "TalkinBot"
        assert bot._complete_pending_room_list({"_occupants_room": "BlueBird", "users": [{}]})

    assert bot.bot_room_roles[bot_module._norm_room("BlueBird")] == "owner"
    assert any("أونر (Owner)" in text for _room, text in messages)
    assert not bot._pending_room_lists
    assert not bot._pending_bot_room_role_checks
    assert timers[0].cancelled


def test_profile_photo_lookup_uses_roster_user_id_and_nested_profiles_value():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.user_photos = {}
    bot.user_profile_ids = {}
    bot.log = lambda *_args: None
    bot._cache_user_photos_from_result({
        "users": [{"1": "FancyUser", "2": "talkin-user-uuid"}]
    })
    assert bot.user_profile_ids[bot_module._norm_user("FancyUser")] == "talkin-user-uuid"

    calls = []

    class Query:
        def __init__(self):
            self.column = self.value = ""

        def select(self, _columns):
            return self

        def eq(self, column, value):
            self.column, self.value = column, value
            return self

        def limit(self, _count):
            return self

        def execute(self):
            calls.append((self.column, self.value))
            rows = ([{
                "id": "talkin-user-uuid",
                "username": "FancyUser",
                "avatar": {"image": {"src": "https://cdn.example/fancy.jpg"}},
            }] if self.column == "id" else [])
            return SimpleNamespace(data=rows)

    class Client:
        def table(self, _name):
            return Query()

    bot.db = SimpleNamespace(client=Client())
    assert bot._lookup_profile_photo("FancyUser") == "https://cdn.example/fancy.jpg"
    assert calls[0] == ("id", "talkin-user-uuid")


def test_profile_photo_decoder_accepts_nested_roster_photo_url():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    users = bot._extract_room_list_users({
        "users": [{"1": "FancyUser", "2": "id-2", "3": {"image": {"url": "//cdn.example/photo.webp"}}}]
    })
    assert users[0]["photo"] == "https://cdn.example/photo.webp"


def test_only_room_owner_can_bypass_verification_for_explicit_live_music():
    bot = SimpleNamespace(room_users={
        "Hall": {"FancyOwner": "owner", "RoomAdmin": "admin"},
    })
    assert bot_module._owner_live_music_allowed(bot, "Hall", "FancyOwner", "بث اسم الأغنية")
    assert not bot_module._owner_live_music_allowed(bot, "Hall", "RoomAdmin", "بث اسم الأغنية")
    assert not bot_module._owner_live_music_allowed(bot, "Hall", "FancyOwner", ".تشغيل اسم الأغنية")


def test_unverified_room_owner_broadcast_reaches_live_music_handler():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.room = "Hall"
    bot.known_rooms = set()
    bot.connected_rooms = set()
    bot.blocked_rooms = set()
    bot._blocked_room_notices = set()
    bot.room_users = {"Hall": {"OwnerName": "owner", "TalkinBot": "owner"}}
    bot.bot_blocked_users = set()
    bot._bot_block_notice_at = {}
    bot.banned_words = set()
    bot.music_last = {}
    bot.music_current = {}
    bot.reaction_targets = {}
    bot.log = lambda *_args, **_kwargs: None
    sent, calls = [], []
    bot.send_room_text = lambda room, text: sent.append((room, text)) or True
    bot.send_private_text = lambda *_args, **_kwargs: True
    bot.handle_music_command = lambda *args, **kwargs: calls.append((args, kwargs)) or True
    bot._remember_inflight_command = lambda *_args, **_kwargs: None
    bot._report_monitored_event = lambda *_args, **_kwargs: None
    bot._complete_pending_room_list_text = lambda *_args, **_kwargs: False
    bot._handle_telegram_log_command = lambda *_args, **_kwargs: False
    bot._is_duplicate_incoming = lambda *_args, **_kwargs: False
    bot._handle_kemin_command = lambda *_args, **_kwargs: False
    bot._handle_top_wagerers = lambda *_args, **_kwargs: False
    bot._handle_random_picture_command = lambda *_args, **_kwargs: False
    bot._handle_lookalike_command = lambda *_args, **_kwargs: False
    bot._handle_explore_command = lambda *_args, **_kwargs: False
    bot._handle_reaction_command = lambda *_args, **_kwargs: False
    bot._route_room_game_input = lambda *_args, **_kwargs: False
    bot._remember_bot_action = lambda *_args, **_kwargs: None

    with patch.object(bot_module, "_verified_identity_candidate", return_value=""), patch.object(
        bot_module, "_looks_like_bot_command", return_value=True
    ), patch.object(bot_module, "_room_moderation_config", return_value={"words": []}), patch.object(
        bot_module, "_room_protection_cfg", return_value={"flood": False, "swear": False, "repeat_limit": 20}
    ), patch.object(bot_module, "_verification_notice", return_value="verify"), patch.object(
        bot_module, "BOT_ID", "TalkinBot"
    ):
        bot.handle_room_event({"room_event": {
            1: "text", 2: "OwnerName", 6: "بث اسم الاغنية", 13: "Hall", 22: "OwnerName",
        }})

    assert calls and calls[0][1].get("live_stream") is True
    assert not any("غير موثق" in text for _room, text in sent)


def test_my_picture_acknowledges_before_profile_network_lookup(monkeypatch):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.user_photos = {}
    bot._profile_picture_busy = set()
    bot.stop_event = threading.Event()
    bot.stop_event.set()  # Skip polling; exercise the worker's DB fallback directly.
    replies, media, lookups, threads = [], [], [], []
    bot.send_room_text = lambda room, text: replies.append((room, text)) or True
    bot.send_room_media = lambda *args: media.append(args) or True
    bot._queue_profile_roster_refresh = lambda *_args: True
    bot._lookup_profile_photo = lambda username: lookups.append(username) or "https://cdn.example/avatar.jpg"

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target
            threads.append(self)

        def start(self):
            return None

    monkeypatch.setattr(bot_module.threading, "Thread", DeferredThread)
    with patch.object(bot_module, "_store_profile_photo_for_public_media", return_value=None), patch.object(
        bot_module, "_public_base_url", return_value=""
    ):
        assert bot._handle_random_picture_command("Hall", "صورتي", "FancyUser") is True
        assert replies == []  # User requested silent searching.
        assert lookups == []  # No Supabase/network lookup on the event thread.
        assert len(threads) == 1
        threads[0].target()

    assert lookups == ["FancyUser"]
    assert media == [("Hall", "https://cdn.example/avatar.jpg", "image")]
    assert replies == [("Hall", "صورتك هي الصورة")]
    assert not bot._profile_picture_busy


def test_profile_photo_search_is_silent_when_no_avatar_exists(monkeypatch):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.user_photos = {}
    bot._profile_picture_busy = set()
    bot.stop_event = threading.Event()
    bot.stop_event.set()
    replies = []
    bot.send_room_text = lambda room, text: replies.append((room, text)) or True
    bot._queue_profile_roster_refresh = lambda *_args: True
    bot._lookup_profile_photo = lambda _username: ""
    bot.log = lambda *_args: None

    class InlineThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(bot_module.threading, "Thread", InlineThread)
    assert bot._handle_random_picture_command("Hall", "صورتي", "FancyUser") is True
    assert replies == []
    assert not bot._profile_picture_busy


def test_profile_photo_handler_does_not_claim_internet_photo_command():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    assert bot._handle_random_picture_command("Hall", ".صوره قرود", "FancyUser") is False
    assert bot._handle_random_picture_command("Hall", "صورتك", "FancyUser") is False


def test_internet_picture_command_searches_adult_women_and_sends_hosted_image(monkeypatch, tmp_path):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._internet_picture_busy = set()
    replies, media, threads, queries, verified = [], [], [], [], []
    bot.send_room_text = lambda room, text: replies.append((room, text)) or True
    bot.send_room_media = lambda *args: media.append(args) or True
    bot._verify_public_media_url = lambda url, kind: verified.append((url, kind))

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target
            threads.append(self)

        def start(self):
            return None

    monkeypatch.setattr(bot_module.threading, "Thread", DeferredThread)
    monkeypatch.setattr(bot_module, "_search_lookalike_image", lambda query, **_kwargs: queries.append(query) or "https://source.example/women.jpg")
    monkeypatch.setattr(bot_module, "_search_monkey_image", lambda **_kwargs: None)
    monkeypatch.setattr(bot_module, "_download_lookalike_image", lambda *_args: tmp_path / "random-woman.jpg")
    monkeypatch.setattr(bot_module, "_public_base_url", lambda: "https://media.example")

    assert bot._handle_internet_picture_command("Hall", ".صوره بنات حلوه", "FancyUser") is True
    assert queries == []  # Search is off the room-event thread.
    assert bot._handle_random_picture_command("Hall", ".صوره بنات حلوه", "FancyUser") is False
    threads[0].target()

    assert queries == ["beautiful adult women portraits"]
    assert verified == [("https://media.example/lookalikes/random-woman.jpg", "image")]
    assert media == [("Hall", "https://media.example/lookalikes/random-woman.jpg", "image")]
    assert replies == [("Hall", "صورتك هي الصورة")]
    assert not bot._internet_picture_busy


def test_internet_picture_search_is_silent_when_no_image_is_found(monkeypatch):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._internet_picture_busy = set()
    bot._internet_picture_recent = {}
    replies = []
    bot.send_room_text = lambda room, text: replies.append((room, text)) or True
    bot.send_room_media = lambda *_args: True
    bot.log = lambda *_args: None

    class InlineThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(bot_module.threading, "Thread", InlineThread)
    monkeypatch.setattr(bot_module, "_search_lookalike_image", lambda *_args, **_kwargs: None)
    assert bot._handle_internet_picture_command("Hall", ".صوره بنات حلوه", "FancyUser") is True
    assert replies == []
    assert not bot._internet_picture_busy


def test_random_internet_picture_categories_include_monkeys_and_adults(monkeypatch):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    monkey_query, monkey_label, is_monkey = bot._random_internet_picture_query("قرود")
    men_query, _men_label, men_is_monkey = bot._random_internet_picture_query("شباب وسيمين")
    women_query, _women_label, women_is_monkey = bot._random_internet_picture_query("بنات حلوه")
    assert (monkey_query, monkey_label, is_monkey) == ("monkeys wildlife", "قرود", True)
    assert "adult men" in men_query and not men_is_monkey
    assert "adult women" in women_query and not women_is_monkey

    monkeypatch.setattr(bot_module.secrets, "randbelow", lambda _limit: 29)
    assert bot._random_internet_picture_query("", "male")[2] is True
    assert all("قرود" in query or "monkey" in query for query in bot._picture_search_queries_for_name("Ahmed", "male"))

    monkeypatch.setattr(bot_module.secrets, "randbelow", lambda _limit: 30)
    male_random = bot._random_internet_picture_query("", "male")
    female_random = bot._random_internet_picture_query("", "female")
    unknown_random = bot._random_internet_picture_query("", "unknown")
    assert "adult men" in male_random[0] and not male_random[2]
    assert "adult women" in female_random[0] and not female_random[2]
    assert "adult people" in unknown_random[0] and not unknown_random[2]
    male_queries = bot._picture_search_queries_for_name("Ahmed", "male")
    female_queries = bot._picture_search_queries_for_name("Amira", "female")
    assert all(("adult men" in query or "adult man" in query or "بالغ" in query) and "women" not in query for query in male_queries)
    assert all(
        ("adult women" in query or "adult woman" in query or "بالغ" in query)
        and "adult men" not in query and "handsome" not in query and "شباب" not in query
        for query in female_queries
    )


def test_internet_picture_command_searches_named_user_with_safe_portrait_query(monkeypatch, tmp_path):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot._internet_picture_busy = set()
    replies, media, queries = [], [], []
    bot.send_room_text = lambda room, text: replies.append((room, text)) or True
    bot.send_room_media = lambda *args: media.append(args) or True
    bot._verify_public_media_url = lambda *_args: True
    bot.log = lambda *_args: None

    class InlineThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(bot_module.threading, "Thread", InlineThread)
    monkeypatch.setattr(
        bot_module, "_search_lookalike_image",
        lambda query, **_kwargs: queries.append(query) or "https://source.example/person.jpg",
    )
    monkeypatch.setattr(bot_module, "_search_monkey_image", lambda **_kwargs: None)
    monkeypatch.setattr(bot_module, "_download_lookalike_image", lambda *_args: tmp_path / "person.jpg")
    monkeypatch.setattr(bot_module, "_public_base_url", lambda: "https://media.example")

    assert bot._handle_internet_picture_command("Hall", ".صوره FancyUser", "Requester") is True
    assert queries == ["FancyUser portrait safe for work"]
    assert media == [("Hall", "https://media.example/lookalikes/person.jpg", "image")]
    assert replies == [("Hall", "صورتك هي الصورة")]


def test_lookalike_commands_use_safe_gender_matched_searches(monkeypatch, tmp_path):
    for command, target, gender, expected_query in (
        ("شبيه@Ahmed", "Ahmed", "male", "handsome adult men portrait safe for work"),
        ("شبيهك@Amira", "Amira", "female", "beautiful adult women portrait safe for work"),
    ):
        bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
        bot._lookalike_busy = set()
        bot._lookalike_recent = {}
        bot.room_users = {"Hall": {target: {"gender": gender}}}
        bot.send_room_text = lambda *_args: True
        bot.send_room_media = lambda *_args: True
        bot.log = lambda *_args: None
        bot._capture_room_response_language = lambda *_args: "ar"
        bot._localized_room_worker = lambda _room, _language, worker: worker
        queries = []

        class InlineThread:
            def __init__(self, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(bot_module.threading, "Thread", InlineThread)
        monkeypatch.setattr(bot_module.secrets, "randbelow", lambda _limit: 30)
        monkeypatch.setattr(bot_module.secrets, "choice", lambda choices: choices[0])
        monkeypatch.setattr(
            bot_module, "_search_lookalike_image",
            lambda query, **_kwargs: queries.append(query) or "https://source.example/lookalike.jpg",
        )
        monkeypatch.setattr(bot_module, "_search_monkey_image", lambda **_kwargs: None)
        monkeypatch.setattr(bot_module, "_download_lookalike_image", lambda *_args: tmp_path / "lookalike.jpg")
        monkeypatch.setattr(bot_module, "_public_base_url", lambda: "https://media.example")

        assert bot._handle_lookalike_command("Hall", command, "Requester") is True
        assert queries == [expected_query]


def test_human_image_search_uses_strict_bing_safesearch_without_commons_fallback(monkeypatch):
    calls = []

    class Response:
        text = '{"murl":"https://images.example/adult-portrait.jpg"}'

        @staticmethod
        def raise_for_status():
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(bot_module.requests, "get", fake_get)
    urls = bot_module._search_lookalike_images("handsome adult men portrait", limit=8)

    assert urls == ["https://images.example/adult-portrait.jpg"]
    assert len(calls) == 1  # No unfiltered Wikimedia portrait fallback.
    assert calls[0][0] == "https://www.bing.com/images/search"
    assert calls[0][1]["params"]["adlt"] == "strict"
    assert calls[0][1]["params"]["q"] == "handsome adult men portrait safe for work"


def test_explicit_internet_image_search_is_blocked_without_network(monkeypatch):
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("explicit image query should be blocked before search")

    monkeypatch.setattr(bot_module.requests, "get", fail_if_called)
    assert bot._handle_internet_picture_command("Hall", ".صوره صور مخلة", "FancyUser") is True
    assert bot_module._search_lookalike_images("porn images") == []


def test_native_avatar_roster_refresh_is_per_member_and_not_db_short_circuited():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.ws = object()
    bot.send_query = lambda _query: True
    bot.log = lambda *_args: None
    completed = threading.Event()
    calls = []

    def native_request(room):
        calls.append(room)
        if len(calls) == 2:
            completed.set()
        return True

    bot._request_native_profile_roster = native_request
    assert bot._queue_profile_roster_refresh("Hall", "Alice")
    assert bot._queue_profile_roster_refresh("Hall", "Bob")
    assert completed.wait(2)
    assert sorted(calls) == ["Hall", "Hall"]


def test_database_roster_refresh_caches_profile_ids_for_avatar_lookup():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.db = SimpleNamespace(room_users=lambda _room: [{
        "username": "Alice", "user_id": "profile-123", "role": "member",
    }])
    bot.room_users = {}
    bot.user_profile_ids = {}
    bot.user_photos = {}
    bot.last_joined_room = ""
    with patch.object(bot_module, "_remember_roster"):
        assert bot.request_room_occupants("Hall")
    assert bot.user_profile_ids[bot_module._norm_user("Alice")] == "profile-123"


def test_join_event_does_not_treat_room_event_to_field_as_avatar():
    assert bot_module._extract_room_event_profile_photo({
        3: "https://chat.example/recipient", 17: "Alice",
    }) == ""
    assert bot_module._extract_room_event_profile_photo({
        3: "https://chat.example/recipient", "avatar_url": "https://cdn.example/alice.jpg",
    }) == "https://cdn.example/alice.jpg"
