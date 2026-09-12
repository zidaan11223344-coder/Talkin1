from bot import TalkinBot

bot = object.__new__(TalkinBot)
bot.sent = []
bot.media = []
bot.send_room_text = lambda room, text: bot.sent.append((room, text))
bot.send_room_media = lambda room, url, kind: bot.media.append((room, url, kind))
# Use the real helper with the repository asset and a deterministic public URL.
import bot as module
old = module._public_base_url
module._public_base_url = lambda: "https://example.test"
try:
    bot._send_game_result("adam", "result", "dice")
finally:
    module._public_base_url = old
assert bot.sent == [("adam", "result")]
assert bot.media == [("adam", "https://example.test/assets/game_dice.jpg", "image")]
print("game result image: PASS")
