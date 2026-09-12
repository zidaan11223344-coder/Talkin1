from pathlib import Path
import bot

assets = Path(bot.BASE_DIR) / 'assets'
# All artwork files must be represented by a game mapping and be readable.
files = {p.name for p in assets.iterdir() if p.is_file() and (p.stem.startswith('game_') or p.name in {'million_game.jpg','slap_action.jpg','war_game.jpg','war_game.png'})}
used = set(bot.GAME_IMAGE_FILES.values())
missing = sorted(files - used)
assert not missing, missing
assert all((assets / name).is_file() for name in used)

# Every image-game command must resolve to a real image key.
assert all(key in bot.GAME_IMAGE_FILES for key, _ in bot.GAME_COMMANDS.values())
print(f'all game assets: PASS ({len(files)} images, {len(bot.GAME_COMMANDS)} image commands)')
