import bot

assert bot._is_publish_command('انشر')
assert bot._is_publish_command('انشر@الوصف')
assert bot._is_publish_command('نشر@وصف')
assert bot._publish_description('انشر@الوصف') == 'الوصف'
assert bot._looks_like_bot_command('مشاركه احمد')
assert bot._looks_like_bot_command('مشاركة @احمد')
assert bot._looks_like_bot_command('.تشغيل اغنية')
assert bot._looks_like_bot_command('بث اغنية')

obj = object.__new__(bot.TalkinBot)
obj.music_current = {'alice': {'title': 'Song', 'url': 'https://example/song.mp3', 'duration': 12}}
obj.private_text = []
obj.private_media = []
obj.room_text = []
obj.send_private_text = lambda user, text: obj.private_text.append((user, text))
obj.send_private_media = lambda user, url, kind, duration: obj.private_media.append((user, url, kind, duration))
obj.send_room_text = lambda room, text: obj.room_text.append((room, text))
assert obj.share_last_music('Alice', 'Bob', 'room')
assert obj.private_media == [('Bob', 'https://example/song.mp3', 'audio', 12)]

payloads = []
media_obj = object.__new__(bot.TalkinBot)
media_obj._verify_public_media_url = lambda *args: True
media_obj.send_query = lambda payload: payloads.append(payload) or True
assert media_obj.send_private_media('Bob', 'https://example/song.mp3', 'audio', 12)
fields = bot.decode_message(payloads[0])
assert 5 in fields  # empty body is required by Talkin private audio packets
print('publish/music commands: PASS')
