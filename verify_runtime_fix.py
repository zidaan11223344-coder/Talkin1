import threading
import bot

obj = object.__new__(bot.TalkinBot)
obj._incoming_seen = {}
obj._incoming_seen_lock = threading.Lock()
assert obj._is_duplicate_incoming('room', ('text', 'r', 'u', 'بنك', ''), 'same-id') is False
assert obj._is_duplicate_incoming('room', ('text', 'r', 'u', 'بنك', ''), 'same-id') is True
assert obj._is_duplicate_incoming('room', ('text', 'r', 'u', 'بنك', ''), 'same-id-2') is False

# The ludo handler must normalize Arabic-Indic digits before matching 1..4.
obj.ludo_games = {'ludo:r': {
    'players': ['user'], 'tokens': {'user': 0}, 'rooms': {'r'},
    'origin_room': 'r', 'max_players': 0, 'bot': False,
    'started': False, 'turn': 0,
}}
obj._board_game_cooldown_notice = lambda room, sender: True
obj._schedule_board_game_timeout = lambda *args, **kwargs: None
sent = []
obj.send_room_text = lambda room, text: sent.append(text)
obj._send_game_cover = lambda *args, **kwargs: None
obj._broadcast_game_start = lambda *args, **kwargs: None
assert obj._ludo_command('r', 'user', '١') is True
assert obj.ludo_games['ludo:r']['max_players'] == 1
assert obj.ludo_games['ludo:r']['bot'] is True
print('runtime fixes: PASS')
