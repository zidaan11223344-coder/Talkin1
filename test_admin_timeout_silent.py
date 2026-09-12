from collections import defaultdict
import threading
import bot

obj = object.__new__(bot.TalkinBot)
obj.pending_admin_actions = {
    ('room', 'target', 'outcast'): {
        'room': 'room', 'target': 'target', 'requester': 'master'
    }
}
obj.pending_admin_lock = threading.Lock()
obj.sent = []
obj.send_room_text = lambda room, text: obj.sent.append((room, text))
obj.log = lambda *args: None
old_sleep = bot.time.sleep
bot.time.sleep = lambda seconds: None
try:
    obj._admin_confirmation_timeout(('room', 'target', 'outcast'))
finally:
    bot.time.sleep = old_sleep
assert obj.sent == []
print('admin timeout silent: PASS')
