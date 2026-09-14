import os
os.environ['BOT_MASTER']='master'
import bot
from collections import defaultdict

obj=object.__new__(bot.TalkinBot)
obj.room_users=defaultdict(dict)
obj.room_users['room']['owner']='owner'
obj.room='room'
obj.known_rooms=set(); obj.connected_rooms=set(); obj.blocked_rooms=set(); obj._blocked_room_notices=set()
obj._incoming_seen={}; obj._incoming_seen_lock=__import__('threading').Lock()
obj.pending_admin_actions={}; obj.pending_admin_lock=__import__('threading').Lock()
obj.last_messages=defaultdict(list); obj.auto_replies_enabled=False; obj.auto_replies={}
obj._room_repeat_state=defaultdict(lambda: defaultdict(list))
obj._master_reply_local=__import__('threading').local()
obj.banned_words=set()
obj.moderation_enabled=False
obj.send_room_text=lambda room,text: obj.sent.append((room,text))
obj.send_private_text=lambda user,text: obj.sent.append((user,text))
obj.send_admin=lambda room,user,op: obj.admin.append((room,user,op))
obj.send_query=lambda payload: None
obj.log=lambda *a: None
obj.sent=[]; obj.admin=[]
# Owner enables room protection and sets limit.
assert obj._handle_management_command('room','تشغيل الحماية','owner')
assert obj._handle_management_command('room','mr@3','owner')
assert bot._room_moderation_config('room')['enabled'] is True
# Repeated messages warn at penultimate and ban at limit.
for _ in range(3):
    obj.handle_room_event({'room_event':{1:'text',2:'user',6:f'رسالة {_+1}',13:'room',41:str(_+1)}})
assert obj.admin == [('room','user','ban')]
assert any('تكرار مشبوه' in x[1] for x in obj.sent)
# Same text can also trigger the configured limit, even when senders differ.
obj.admin=[]; obj.sent=[]
assert obj._handle_management_command('room','mr@5','owner')
for i, user in enumerate(('a','b','c','d','e')):
    obj.handle_room_event({'room_event':{1:'text',2:user,6:'نفس النص',13:'room',41:f't{i+10}'}})
assert obj.admin == [('room','e','ban')]
# Blocked join gives blocked guidance, not already-registered message.
obj.blocked_rooms={'blocked'}; obj.known_rooms=set(); obj.connected_rooms=set(); obj._last_join_sent={}; obj._join_lock=__import__('threading').Lock(); obj.ws=None
obj.join_room=lambda room: False
obj._handle_management_command('', 'دخول blocked', 'user', is_private=True)
assert any('البوت محظور' in x[1] for x in obj.sent)
print('new security: PASS')
