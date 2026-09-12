import bot

# Every image-game command is recognized as a bot command and therefore
# reaches the verification gate instead of silently running for guests.
for command in bot.GAME_COMMANDS:
    assert bot._looks_like_bot_command(command), command

# The user-facing request is intended for the room; the notice itself must
# direct the user to the master without relying on a private response.
notice = bot._verification_notice()
assert 'ليس موثقاً' in notice
assert 'مراسلة الماستر' in notice

# Non-master verified users are supported by the media/game handlers; the
# command routing no longer checks _is_master_name for those features.
source = open('bot.py', encoding='utf-8').read()
assert 'if self.handle_game_command(room, body, frm):' in source
assert 'if self.handle_music_command(room, body, frm):' in source
assert 'if self.handle_gift_command(room, body, frm):' in source
print('verified permissions: PASS')
