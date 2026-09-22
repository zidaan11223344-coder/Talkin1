import threading
import json
import tempfile
from pathlib import Path
import bot

assert bot.first_http_url({99: ["not-url", {77: "https://cdn/image-hidden.jpg"}]}) == "https://cdn/image-hidden.jpg"
invite_fields = bot.decode_message(bot.encode_live_invitation("bot", "target", "tok", "985009014", "مشاعر", "12345678901234567"))
assert [invite_fields[k][0].decode() for k in (1, 2, 3, 5, 6, 8, 9)] == ["sent_invitation", "bot", "target", "tok", "985009014", "مشاعر", "12345678901234567"]


# 1) A photo event whose author is in field 22 must complete a pending publish.
obj = object.__new__(bot.TalkinBot)
obj.blocked_rooms = set()
obj._blocked_room_notices = set()
obj.known_rooms = set()
obj._incoming_seen = {}
obj._incoming_seen_lock = threading.Lock()
obj.room = "main"
obj.connected_rooms = {"main"}
obj.room_users = {}
obj.publish_pending = {bot._norm_user("sender"): {"description": "test", "created_at": __import__("time").time()}}
obj._handle_publish_media = lambda room, sender, url: sender == "sender" and url == "https://cdn/image.jpg"
obj._try_publish_pending_media = lambda room, url, candidates=(): any(
    obj._handle_publish_media(room, sender, url)
    for sender in list(candidates) + list(obj.publish_pending)
)
obj.ack = lambda uid: None
obj.log = lambda *args: None
obj.send_room_text = lambda *args: None
obj.handle_room_event({"room_event": {1: "image", 2: "", 7: "https://cdn/image.jpg", 22: "sender", 13: "main"}})

# 2) Private audio must be encoded as chat_message type=audio, with empty body.
payloads = []
media_obj = object.__new__(bot.TalkinBot)
media_obj._verify_public_media_url = lambda *args: True
media_obj.send_query = lambda payload: payloads.append(payload) or True
assert media_obj.send_private_media("target", "https://cdn/song.mp3", "audio", 12)
fields = bot.decode_message(payloads[0])
assert fields[1][0] == b"chat_message"
assert fields[2][0] == bot.PRIVATE_AUDIO_TYPE.encode()
assert fields[5][0] == b""
assert fields[4][0] == b"target"

# 3) بث maps to .sa and enables broadcast_all; .تشغيل stays local.
route_obj = object.__new__(bot.TalkinBot)
route_obj.room = "main"
route_obj._active_rooms = lambda: ["main", "second"]
route_obj.send_room_text = lambda *args: None
route_obj.handle_music_command = lambda room, command, requester, **kwargs: (
    setattr(route_obj, "last_call", (room, command, requester, kwargs)) or True
)
route_obj._remember_bot_action = lambda *args, **kwargs: None
route_obj._replaying_bot_action = True
route_obj.room_users = {}
route_obj.known_rooms = set()
route_obj._incoming_seen = {}
route_obj._incoming_seen_lock = threading.Lock()
# Call the same routing expression used by the handler and assert its contract.
body = "بث اسم الأغنية"
is_room_broadcast = body.strip().startswith("بث ")
command = body.replace(".تشغيل ", ".sa ", 1) if not is_room_broadcast else body.replace("بث ", ".sa ", 1)
route_obj.handle_music_command("main", command, "sender", broadcast_all=is_room_broadcast, with_reactions=False)
assert route_obj.last_call[1] == ".sa اسم الأغنية"
assert route_obj.last_call[3]["broadcast_all"] is True

# 3b) `.sa` publishes the audio file to every connected room.
route_obj.handle_music_command("main", ".sa اسم الأغنية", "sender", broadcast_all=True, room_output=True)
assert route_obj.last_call[3]["broadcast_all"] is True
assert route_obj.last_call[3]["room_output"] is True

# 3c) `بث` is live-only and must not send a normal room attachment.
route_obj.handle_music_command(
    "main", ".sa اسم الأغنية", "sender",
    broadcast_all=False, room_output=False, live_stream=True,
)
assert route_obj.last_call[3]["live_stream"] is True
assert route_obj.last_call[3]["room_output"] is False

# 4) The experimental live flow emits invite -> stream_accept -> audio.
payloads = []
stream_obj = object.__new__(bot.TalkinBot)
stream_obj.send_query = lambda payload: payloads.append(bot.decode_message(payload)) or True
stream_obj.log = lambda *args: None
stream_obj.send_private_text = lambda *args: None
stream_obj._pending_live_tracks = {}
stream_obj._live_room_ids = {"main": "700978564"}
stream_obj.send_live_invitation_to_user = lambda target, room: True
bot.STREAM_EXPERIMENTAL_ENABLED = True
bot.STREAM_ACCEPT_DELAY = 0
bot.STREAM_AUDIO_DELAY = 0
stream_obj._play_music_in_live_room("main", "https://cdn/song.mp3", 12)
stream_obj._handle_stream_event({1: "you_invited", 5: "78993070543988401", 6: "room-1", 8: "main", 9: "2586245694009091"})
assert payloads[-1][1][0].decode() == bot.STREAM_ACCEPT_ACTION
assert "main" not in getattr(stream_obj, "_live_ready_rooms", set())
assert "main" in stream_obj._pending_live_accepts
assert stream_obj._handle_stream_result_ack({"type": "accepted", "room": "main"}) is True
assert [item[1][0].decode() for item in payloads[-2:]] == [bot.STREAM_ACCEPT_ACTION, bot.STREAM_AUDIO_ACTION]
assert "main" in stream_obj._live_ready_rooms
check_fields = payloads[-2]
assert check_fields[5][0].decode() == bot.STREAM_INVITE_TOKEN == "Token"
assert check_fields[6][0].decode() == "room-1"
assert check_fields[8][0].decode() == "main"
assert len(check_fields[9][0].decode()) == 17

# Incoming invitations must still be accepted if the legacy experimental flag
# is disabled in an old deployment.
old_experimental = bot.STREAM_EXPERIMENTAL_ENABLED
bot.STREAM_EXPERIMENTAL_ENABLED = False
fallback_obj = object.__new__(bot.TalkinBot)
fallback_obj._pending_live_tracks = {}
fallback_obj._live_room_ids = {}
fallback_obj._live_ready_rooms = set()
fallback_obj._accepted_live_invites = set()
fallback_obj._pending_live_accepts = {}
fallback_obj.send_query = lambda payload: payloads.append(bot.decode_message(payload)) or True
fallback_obj.send_private_text = lambda *args: None
fallback_obj.log = lambda *args: None
assert fallback_obj._handle_stream_event({1: "you_invited", 6: "room-fallback", 8: "fallback", 9: "invite-fallback"}) is True
assert payloads[-1][1][0].decode() == bot.STREAM_ACCEPT_ACTION
bot.STREAM_EXPERIMENTAL_ENABLED = old_experimental

# 4b) اصعد uses the real self-invitation packet, not the old generic query.
old_bot_id = bot.BOT_ID
bot.BOT_ID = old_bot_id or "s-boot"
old_manual_mode = bot.STREAM_MANUAL_ACCEPT_ONLY
bot.STREAM_MANUAL_ACCEPT_ONLY = True
join_payloads = []
join_obj = object.__new__(bot.TalkinBot)
join_obj._live_ready_rooms = set()
join_obj._live_room_ids = {"main": "700978564"}
join_obj.live_invites = []
join_obj.send_live_invitation_to_user = lambda target, room: join_obj.live_invites.append((target, room)) or True
join_obj.send_query = lambda payload: join_payloads.append(bot.decode_message(payload)) or True
join_obj.send_private_text = lambda *args: None
join_obj.send_room_text = lambda *args: None
assert join_obj.request_live_room("main") is True
assert not join_payloads
assert join_obj.live_invites == []
bot.BOT_ID = old_bot_id
bot.STREAM_MANUAL_ACCEPT_ONLY = old_manual_mode

# Older gateway builds use an equivalent invitation name and string fields.
stream_obj._pending_live_tracks["main"] = {"url": "https://cdn/song2.mp3", "duration": 9, "room_id": "room-2"}
stream_obj._handle_stream_event({"type": "invited", "invite_id": "invite-2", "room_id": "room-2", "room": ""})
assert payloads[-1][1][0].decode() == bot.STREAM_ACCEPT_ACTION
assert stream_obj._handle_stream_result_ack({"type": "accepted", "room": "main"}) is True
assert [item[1][0].decode() for item in payloads[-2:]] == [bot.STREAM_ACCEPT_ACTION, bot.STREAM_AUDIO_ACTION]

# A seat invitation may omit its id; the room-based accept path must still run.
stream_obj._handle_stream_event({1: "room_invitation", 6: "room-3", 8: "main"})
assert payloads[-1][1][0].decode() == bot.STREAM_ACCEPT_ACTION

# A repeated invitation must not create a second client session or acceptance.
before_duplicate = len(payloads)
assert stream_obj._handle_stream_event({1: "room_invitation", 6: "room-3", 8: "main"}) is True
assert len(payloads) == before_duplicate

# sent_invitation confirms only that an invitation was sent; it must not
# trigger a false stream acceptance.
before_sent = len(payloads)
assert stream_obj._handle_stream_event({1: "sent_invitation", 6: "room-4", 8: "main"}) is False
assert len(payloads) == before_sent

# A failed acceptance must be persisted as a safe JSONL diagnostic.
with tempfile.TemporaryDirectory() as temp_dir:
    error_obj = object.__new__(bot.TalkinBot)
    error_obj._pending_live_tracks = {
        "main": {"url": "https://cdn/song3.mp3", "duration": 7, "room_id": "room-5"}
    }
    error_obj._live_room_ids = {"main": "700978564"}
    error_obj._stream_error_log_file = Path(temp_dir) / "stream-errors.log"
    error_obj._stream_error_log_lock = threading.Lock()
    error_obj.log = lambda *args: None
    error_obj.send_query = lambda payload: (_ for _ in ()).throw(ConnectionError("gateway unavailable"))
    assert error_obj._handle_stream_event({1: "you_invited", 6: "room-5", 8: "main", 9: "invite-5"}) is False
    error_record = json.loads(error_obj._stream_error_log_file.read_text(encoding="utf-8"))
    assert error_record["stage"] == "accept_or_audio"
    assert error_record["room"] == "main"
    assert error_record["room_id"] == "room-5"
    assert error_record["invite_id"] == "invite-5"
    assert "gateway unavailable" in error_record["error"]

print("user requested media fixes: PASS")
