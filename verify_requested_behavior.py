import json
import bot

assert bot._has_auto_reply_entries({"enabled": True, "auto_replies": {}}) is False
assert bot._has_auto_reply_entries({"auto_replies": {"هلا": {"replies": ["أهلًا"]}}}) is True

with open(bot.REPLIES_FILE, encoding="utf-8") as handle:
    replies = json.load(handle)
auto = replies["auto_replies"]
assert len(auto) == 31
for trigger in ("من انا", "من أنا", "اسمي", "لقبي"):
    assert trigger in auto and auto[trigger]["replies"]
assert bot._auto_reply_key("من أنا؟") == bot._auto_reply_key("من انا")
assert bot._auto_reply_key("لقبي؟") == bot._auto_reply_key("لقبي")

with open(bot.MODERATION_FILE, encoding="utf-8") as handle:
    moderation = json.load(handle)
assert moderation["enabled"] is False
assert len(moderation["words"]) == 322

obj = object.__new__(bot.TalkinBot)
assert obj._render_auto_reply("الرد هنا", "@محمد", "غرفة") == "محمد الرد هنا"
assert obj._render_auto_reply("@{username} الرد هنا", "@محمد", "غرفة") == "محمد الرد هنا"
obj.auto_replies = auto
assert obj._auto_reply_variants("من أنا؟")
assert obj._auto_reply_variants("لقبي؟")
assert obj._run_game_command_async("غرفة", "انا", "محمد") is False
assert obj._run_game_command_async("غرفة", "بوت", "محمد") is False
obj.banned_words = {"كلمة سيئة"}
obj.moderation_enabled = False
assert obj._find_publish_filter_hit("هذا نص فيه كلمة سيئة") == "كلمة سيئة"
print("requested behavior: PASS")

blocked = bot._publish_banned_users()
assert blocked
print("backup publish bans: PASS", len(blocked))
