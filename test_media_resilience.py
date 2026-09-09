import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import media_music_gifts as media

class FakeYDL:
    extract_calls = 0
    download_calls = 0
    def __init__(self, opts): self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def extract_info(self, url, download=False):
        FakeYDL.extract_calls += 1
        if FakeYDL.extract_calls == 1:
            raise RuntimeError('ERROR: [youtube] test: The page needs to be reloaded.')
        if download:
            FakeYDL.download_calls += 1
            Path(media.MUSIC_DIR / 'test123.mp3').write_bytes(b'test')
        return {'id': 'test123', 'title': 'Test', 'uploader': 'Tester', 'duration': 10,
                'webpage_url': 'https://www.youtube.com/watch?v=test123'}
    def download(self, urls):
        FakeYDL.download_calls += 1
        Path(media.MUSIC_DIR / 'test123.mp3').write_bytes(b'test')

class FakeDL:
    YoutubeDL = FakeYDL

old = media.yt_dlp
old_attempts = os.environ.get('YOUTUBE_ATTEMPTS')
try:
    media.yt_dlp = FakeDL()
    os.environ['YOUTUBE_ATTEMPTS'] = '2'
    result = media.search_download_youtube('test song')
    assert result['path'].exists()
    assert FakeYDL.extract_calls >= 2
    assert FakeYDL.download_calls == 1
    print('media resilience test: PASS')
finally:
    media.yt_dlp = old
    if old_attempts is None: os.environ.pop('YOUTUBE_ATTEMPTS', None)
    else: os.environ['YOUTUBE_ATTEMPTS'] = old_attempts
    try: (media.MUSIC_DIR / 'test123.mp3').unlink()
    except FileNotFoundError: pass
