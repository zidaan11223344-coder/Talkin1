from collections import defaultdict
import threading
import bot

# Immediate moderation acknowledgement is sent without waiting for an event.
obj = object.__new__(bot.TalkinBot)
obj.pending_admin_actions = {}
obj.pending_admin_lock = threading.Lock()
obj.send_admin = lambda room, target, operation: None
obj.send_room_text = lambda room, text: obj.sent.append((room, text))
obj.send_private_text = lambda user, text: None
obj.log = lambda *args: None
obj.sent = []
assert obj.request_admin_action('room', 'target', 'ban', 'master')
assert obj.sent == [('room', '✅ تم أمر حظر @target بنجاح.')]

# Games and image mappings are disabled/removed.
assert bot.GAME_COMMANDS == {}
assert bot.GAME_IMAGE_FILES == {}
assert bot._looks_like_bot_command('bl@target')
assert bot._looks_like_bot_command('دخول room')
print('requested changes: PASS')

# Normal image events are ignored silently.
obj2 = object.__new__(bot.TalkinBot)
obj2.room_users = defaultdict(dict)
obj2.known_rooms = set()
obj2.room = 'room'
obj2.custom_welcome_enabled = False
obj2.pending_admin_actions = {}
obj2.pending_admin_lock = threading.Lock()
obj2.sent = []
obj2.send_room_text = lambda room, text: obj2.sent.append((room, text))
obj2.send_private_text = lambda user, text: obj2.sent.append((user, text))
obj2.ack = lambda uid: None
obj2._handle_publish_media = lambda *args, **kwargs: False
obj2.handle_room_event({'room_event': {1: 'image', 6: 'room', 7: 'https://example/image.jpg', 22: 'guest'}})
assert obj2.sent == []
print('silent image handling: PASS')
