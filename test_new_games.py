from collections import defaultdict
import random
import threading
import bot

obj = object.__new__(bot.TalkinBot)
obj.game_lock = threading.Lock()
obj.game_cooldown = defaultdict(float)
obj.wager_waiting = {}
obj.crop_plots = {}
obj.fruit_games = {}
obj.sent = []
obj.media = []
obj.send_room_text = lambda room, text: obj.sent.append((room, text))
obj.send_room_media = lambda room, url, kind: obj.media.append((room, url, kind))
obj._send_game_result = lambda room, text, key: (obj.sent.append((room, text)), obj.media.append((room, key)))
obj.log = lambda *args: None

old_points = bot._get_points
old_add = bot._add_points
old_master = bot._is_master_name
old_random_choice = bot.random.choice
old_random_randint = bot.random.randint
balances = {'alice': 100, 'bob': 100}
bot._get_points = lambda u: balances.get(str(u).casefold(), 0)
bot._add_points = lambda u, n: balances.__setitem__(str(u).casefold(), balances.get(str(u).casefold(), 0) + int(n)) or balances[str(u).casefold()]
bot._is_master_name = lambda u: False
try:
    assert obj.handle_game_command('room-a', 'مراهنة@20', 'alice')
    assert any('جاري البحث عن خصم' in text for _, text in obj.sent)
    assert obj.handle_game_command('room-b', 'مراهنة@20', 'bob')
    assert balances['alice'] + balances['bob'] == 200
    assert obj.media[-1] == ('room-b', 'bet') or obj.media[-1] == ('room-a', 'bet')

    obj.sent.clear(); obj.crop_plots[('alice', '🍎')] = 0
    assert obj.handle_game_command('room-a', 'زرع@🍎', 'alice')
    assert any('حصدت محصول' in text for _, text in obj.sent)

    obj.sent.clear()
    old_random_choice = bot.random.choice
    bot.random.choice = lambda seq: '🍎'
    assert obj.handle_game_command('room-a', 'فيس@🍎', 'alice')
    assert any('تمت المطابقة' in text for _, text in obj.sent)
finally:
    bot._get_points = old_points
    bot._add_points = old_add
    bot._is_master_name = old_master
    bot.random.choice = old_random_choice
    bot.random.randint = old_random_randint

assert bot.GAME_IMAGE_FILES['bet'] == 'game_bet.jpg'
assert bot.GAME_IMAGE_FILES['million'] == 'game_million.jpg'
assert bot._looks_like_bot_command('مليون')
assert bot._looks_like_bot_command('مراهنة@25')
assert bot._looks_like_bot_command('زرع@🍎')
print('new games: PASS')
