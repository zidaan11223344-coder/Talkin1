import os
from pathlib import Path
os.environ['PUBLIC_BASE_URL'] = 'https://example.test'
import media_music_gifts as m
url = m.gift_card_url('1', 'SenderUser', 'ReceiverUser')
assert url.startswith('https://example.test/media/gifts/')
files = list((m.MEDIA_DIR / 'gifts').glob('gift_01_*.png'))
assert files and files[-1].stat().st_size > 1000
print('gift card test: PASS', files[-1])
for p in files: p.unlink()
