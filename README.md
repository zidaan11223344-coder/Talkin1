TalkinChat Bot V8

Changes from V7:
- Uses AuthResult.server as the authoritative WebSocket port.
- Defaults SOCKET_PORT to 5335 instead of 5333.
- A normal WebSocket read timeout no longer causes a reconnect.
- ping/pong frames are handled without disconnecting.
- Keeps V7 login, load_list_new bootstrap, room join, message reception and moderation commands.

Run in Pydroid:
python bot.py
