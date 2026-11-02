import threading
from unittest.mock import patch

import bot as bot_module


def _minimal_bot():
    bot = bot_module.TalkinBot.__new__(bot_module.TalkinBot)
    bot.stock_pending = {}
    bot._stock_auto_gold_pending = {}
    bot._pending_bomb_targets = {}
    bot.ludo_games = {}
    bot.snake_games = {}
    bot.pending_bot_choices = {}
    bot._wallet_handle_next_page = lambda *_args: False
    bot._handle_pending_bot_choice = lambda *_args: False
    bot._snake_command = lambda *_args: False
    bot._ludo_command = lambda *_args: False
    bot._handle_bomb_wire = lambda *_args: False
    bot._configured_room_language = lambda _room: "ar"
    bot.send_room_text = lambda *_args: None
    bot.send_private_text = lambda *_args: None
    return bot


def test_stock_command_opens_asset_menu_instead_of_auto_investing_gold():
    bot = _minimal_bot()
    messages = []
    bot.send_room_text = lambda room, text: messages.append((room, text))
    bot._stock_exchange_game = lambda room, sender: messages.append((room, "MARKET MENU")) or True

    with patch.object(bot_module, "_is_verified_user", return_value=True), \
         patch.object(bot_module, "_games_enabled_for_room", return_value=True):
        assert bot.handle_game_command("Hall", "بورصة", "Player") is True
        assert bot.handle_game_command("Hall", "بورصه", "Player") is True

    assert [text for _room, text in messages] == ["MARKET MENU", "MARKET MENU"]
    assert bot._stock_auto_gold_pending == {}


def test_explicit_gold_auto_still_requires_confirmation():
    bot = _minimal_bot()
    messages = []
    bot.send_room_text = lambda room, text: messages.append((room, text))
    bot._stock_market_is_open = lambda: False
    bot._start_stock_market_round = lambda **_kwargs: {"id": 5}
    bot._stock_market_invest = lambda room, sender, asset, amount: messages.append(
        (room, f"INVEST:{asset}:{amount}")
    ) or True

    with patch.object(bot_module, "_is_verified_user", return_value=True), \
         patch.object(bot_module, "_games_enabled_for_room", return_value=True), \
         patch.object(bot_module, "_get_points", return_value=40_000_000_000), \
         patch.object(bot_module.time, "time", return_value=1000.0):
        assert bot.handle_game_command("Hall", "gold auto", "Player") is True
    key = (bot_module._norm_room("Hall"), bot_module._norm_user("Player"))
    assert bot._stock_auto_gold_pending[key]["amount"] == 30_000_000_000
    assert "موافق" in messages[-1][1]

    with patch.object(bot_module, "_is_verified_user", return_value=True), \
         patch.object(bot_module, "_games_enabled_for_room", return_value=True), \
         patch.object(bot_module, "_get_points", return_value=40_000_000_000), \
         patch.object(bot_module.time, "time", return_value=1010.0):
        assert bot.handle_game_command("Hall", "موافق", "Player") is True
    assert messages[-1][1] == "INVEST:1:30000000000"
    assert key not in bot._stock_auto_gold_pending


def test_join_does_not_confirm_pending_gold_and_reaches_board_game():
    bot = _minimal_bot()
    key = (bot_module._norm_room("Hall"), bot_module._norm_user("Player"))
    bot._stock_auto_gold_pending[key] = {"amount": 1000, "created": 1000.0}
    joined = []
    bot._ludo_command = lambda room, sender, text: joined.append((room, sender, text)) or True
    invested = []
    bot._stock_market_invest = lambda *args, **kwargs: invested.append((args, kwargs)) or True

    assert bot.handle_game_command("Hall", "join", "Player") is True
    assert joined == [("Hall", "Player", "join")]
    assert bot._stock_auto_gold_pending[key]["amount"] == 1000
    assert invested == []


def test_named_arabic_board_join_routes_to_the_requested_game_only():
    bot = _minimal_bot()
    room_key = bot_module._norm_room("Hall")
    bot.snake_games[f"snake:{room_key}"] = {"players": ["Host"]}
    bot.ludo_games[f"ludo:{room_key}"] = {"players": ["Host"], "started": False}
    routed = []
    bot._run_game_command_async = lambda room, command, sender: routed.append((room, command, sender)) or True

    with patch.object(bot_module, "_is_verified_user", return_value=True):
        assert bot._route_active_board_game_join("Hall", "Player", "انضمام لعبه ثعبان") is True
        assert bot._route_active_board_game_join("Hall", "Player", "انضمام لعبة لودو") is True

    assert routed == [
        ("Hall", "انضمام لعبة ثعبان", "Player"),
        ("Hall", "انضمام لعبة لودو", "Player"),
    ]


def test_named_arabic_join_invokes_only_the_requested_board_game():
    bot = _minimal_bot()
    calls = []

    def board_handler(game, room, sender, command):
        calls.append((game, command))
        return command == "join"

    bot._snake_command = lambda room, sender, command: board_handler("snake", room, sender, command)
    bot._ludo_command = lambda room, sender, command: board_handler("ludo", room, sender, command)

    with patch.object(bot_module, "_is_verified_user", return_value=True), \
         patch.object(bot_module, "_games_enabled_for_room", return_value=True):
        assert bot.handle_game_command("Hall", "انضمام لعبة ثعبان", "Player") is True
        assert bot.handle_game_command("Hall", "انضمام لعبة لودو", "Player") is True

    assert calls == [
        ("snake", "انضمام لعبة ثعبان"), ("ludo", "انضمام لعبة ثعبان"),
        ("snake", "join"),
        ("snake", "انضمام لعبة لودو"), ("ludo", "انضمام لعبة لودو"),
        ("ludo", "join"),
    ]


def test_room_router_still_forwards_confirmation_when_auto_gold_is_pending():
    bot = _minimal_bot()
    key = bot_module._game_choice_key("Hall", "Player")
    bot._stock_auto_gold_pending = {key: {"amount": 1000, "created": 1000.0}}
    bot._capture_room_response_language = lambda *_args: None
    bot._localized_room_worker = lambda _room, _language, worker: worker
    bot._remember_bot_action = lambda *_args, **_kwargs: None
    received = []
    bot.handle_game_command = lambda room, text, sender: received.append((room, text, sender))

    class InlineThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    with patch.object(bot_module.threading, "Thread", InlineThread):
        assert bot._run_game_command_async("Hall", "موافق", "Player") is True
    assert received == [("Hall", "موافق", "Player")]
