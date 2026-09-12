from collections import defaultdict
from bot import TalkinBot

bot = object.__new__(TalkinBot)
bot.room_users = defaultdict(dict)
bot.known_rooms = set()
bot.room = "room1"
bot.pending_admin_actions = {
    ("room1", "target", "outcast"): {
        "requester": "master", "room": "room1", "target": "target", "role": "outcast"
    }
}
import threading
bot.pending_admin_lock = threading.Lock()
bot.sent = []
bot.acks = []
bot.send_private_text = lambda user, text: bot.sent.append((user, text))
bot.ack = lambda uid: bot.acks.append(uid)

bot.handle_room_event({"room_event": {1: "role_changed", 13: "room1", 17: "target", 31: "outcast"}, "uid": "event-1"})
assert ("master", "✅ أكد الخادم حظر @target في الغرفة room1.") in bot.sent
assert ("room1", "target", "outcast") not in bot.pending_admin_actions
assert "target" not in bot.room_users["room1"]
assert bot.acks == ["event-1"]
print("admin confirmation event: PASS")
