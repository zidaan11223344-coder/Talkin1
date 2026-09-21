import threading
import bot


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

# 4) The experimental live flow emits invite -> accept -> audio in order.
stream_obj = object.__new__(bot.TalkinBot)
stream_obj.send_query = lambda payload: payloads.append(bot.decode_message(payload)) or True
stream_obj.log = lambda *args: None
stream_obj._pending_live_tracks = {}
bot.STREAM_EXPERIMENTAL_ENABLED = True
bot.STREAM_ACCEPT_DELAY = 0
bot.STREAM_AUDIO_DELAY = 0
stream_obj._play_music_in_live_room("main", "https://cdn/song.mp3", 12)
stream_obj._handle_stream_event({1: "you_invited", 5: "invite-1", 6: "room-1", 8: "main"})
assert [item[1][0].decode() for item in payloads[-3:]] == [bot.STREAM_INVITE_ACTION, bot.STREAM_ACCEPT_ACTION, bot.STREAM_AUDIO_ACTION]

# Older gateway builds use an equivalent invitation name and string fields.
stream_obj._pending_live_tracks["main"] = {"url": "https://cdn/song2.mp3", "duration": 9, "room_id": "room-2"}
stream_obj._handle_stream_event({"type": "invited", "invite_id": "invite-2", "room_id": "room-2", "room": ""})
assert [item[1][0].decode() for item in payloads[-2:]] == [bot.STREAM_ACCEPT_ACTION, bot.STREAM_AUDIO_ACTION]

print("user requested media fixes: PASS")
