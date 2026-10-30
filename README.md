# TalkinChat V22 - Giant assets + points + masters + VIP + publishing

Railway variables (required):
- BOT_ID
- BOT_PWD
- GROUP_TO_JOIN

Optional:
- BOT_MASTER
- YOUTUBE_COOKIES (optional but recommended for YouTube)
- YOUTUBE_COOKIES_FILE (optional mounted Netscape cookie file; alternative to YOUTUBE_COOKIES)
- SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET (optional Spotify catalog search credentials)
- PUBLIC_MEDIA_URL (recommended; shared public base URL for all generated media, including images, gifts, and audio)
- PUBLIC_BASE_URL and GIFT_PUBLIC_BASE_URL (legacy aliases; PUBLIC_MEDIA_URL takes precedence)
- BOT_ASSETS_DIR (optional local/mounted folder for source images, fonts, and templates; defaults to `assets/` beside `bot.py`)
- BOT_DATA_DIR or PERSISTENT_DATA_DIR (optional writable data folder; generated gift cards go to `generated_gifts/` inside it)
- PIPED_APIS (optional comma-separated Piped API instances; auto-discovery is attempted)
- MUSIC_MAX_SECONDS=900
- MUSIC_COOLDOWN=15

For a non-Railway host, set `PUBLIC_MEDIA_URL` in `.env` to the externally reachable
URL, including scheme and allocated port, for example
`http://us-iad01.altare.global:25991`. `PUBLIC_BASE_URL` and
`GIFT_PUBLIC_BASE_URL` are also accepted and take precedence over automatically
detected hosting domains; `PUBLIC_MEDIA_URL` takes priority over both. The media
server uses the host-provided `PORT`, falls back to `ASSET_HTTP_PORT`, then to
`8080`, and listens on `0.0.0.0`. Keep `ASSET_HTTP_ENABLED=1`.

Source gift/game images and the gift template (`gift_template_elegant.png`) are read
from `BOT_ASSETS_DIR` (default: this repository's `assets/` folder). Point it to a
mounted local folder only if that folder contains the expected image/font filenames;
a GitHub repository name alone is not a filesystem path. Generated gift cards, with
their overlays, are stored in `${DATA_DIR}/generated_gifts/`; `DATA_DIR` resolves from
`BOT_DATA_DIR`, then `PERSISTENT_DATA_DIR`, then `./data`, and cards are served at
`/gifts/`. `GITHUB_REPO` (default `zidaan11223344-coder/Talkin4`) is used for JSON
persistent-state backups, not for loading image assets. Platform variables override
`.env`, and `.env` overrides the defaults in `.env.example`.

Spotify track links and text searches can be resolved to a title/artist, then the bot
uses Audius or its configured direct audio/download fallbacks for playback. Spotify's
catalog/API does not provide a general full-track audio URL, so Spotify itself is not
used to bypass its player or stream protected audio.

Local data files:
- `verified_users.json` — verified accounts allowed to use normal commands.
- `vip_users.json` — VIP accounts, also treated as verified.
- `auto_replies.json` — persistent automatic replies.
- `custom_welcomes.json` — persistent custom welcomes.

Commands:
- .sa SONG NAME
- sa@GIFT_NUMBER@USERNAME
- دخول ROOM
- خروج ROOM
- خروج
- انشر
- انشر@DESCRIPTION (then send image)
- sb@USERNAME@POINTS (master)
- mas@USERNAME (owner)
- umas@USERNAME (owner)
- s@USERNAME (master)
- ازالة توثيق@USERNAME (master)
- Vip@USERNAME (master)
- unVip@USERNAME (master)
- اوامر
- نقاطي / توب
- i@USERNAME — send a private invitation to one user (master only)
- توثيق الكل — verify users found in all connected rooms (BOT_MASTER only)

The Giant Chat messages.json is included and used for message templates. Giant assets are copied verbatim under assets/.
