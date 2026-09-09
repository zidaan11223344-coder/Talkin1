import base64
import json
import os
import random
import ssl
import socket
import struct
import hashlib
import threading
import time
import uuid
import subprocess
import traceback
from collections import defaultdict
from pathlib import Path

import requests
try:
    from supabase import create_client
except Exception:
    create_client = None
from dotenv import load_dotenv

load_dotenv()
from media_music_gifts import search_download_youtube, music_url, gift_image, gift_url, gifts_catalog, start_media_server, GIFTS

# ============================================================
# Talkin/ChatP protocol ported from the supplied Android APK.
# The realtime protocol is protobuf over binary WebSocket frames.
# Authentication is protobuf over POST /api?auth_new.
# ============================================================

BOT_ID = os.getenv("BOT_USERNAME", "").strip()
BOT_PWD = os.getenv("BOT_PASSWORD", "")
BOT_MASTER = os.getenv("MASTER_USERNAME", "").strip()
INVITE_SENDER_NAME = "السفير"
GROUP_TO_JOIN = os.getenv("FIRST_ROOM", "").strip()

API_BASE_URL = os.getenv("API_BASE_URL", "https://chatp.net/api?").rstrip("?") + "?"
HOST = os.getenv("HOST_HEADER", "chatp.net").strip()
WS_HOSTS = [x.strip() for x in os.getenv("WS_HOSTS", "chatp.net").split(",") if x.strip()]
DEFAULT_PORT = os.getenv("SOCKET_PORT", "5335").strip()
WS_PATHS = [x.strip() if x.strip().startswith("/") else "/" + x.strip()
            for x in os.getenv("WS_PATHS", "/server").split(",") if x.strip()]
if not WS_PATHS:
    WS_PATHS = ["/server"]
REFERRER_URL = os.getenv("REFERRER_URL", "")
SDK = os.getenv("SDK", "35")
LANGUAGE = os.getenv("LANGUAGE", "").strip()
if not LANGUAGE:
    try:
        from jnius import autoclass
        Locale = autoclass("java.util.Locale")
        LANGUAGE = str(Locale.getDefault().getLanguage())
    except Exception:
        LANGUAGE = "en"
def android_prop(name, fallback=""):
    # Pydroid may not put Android toolbox binaries on PATH, so try the
    # absolute locations used by Android as well.
    for cmd in (("/system/bin/getprop", name), ("getprop", name)):
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2).decode("utf-8", "ignore").strip()
            if out:
                return out
        except Exception:
            pass
    return fallback


def android_secure_id():
    # First try Android's real Java API (the APK obtains its ID from
    # Settings.Secure.ANDROID_ID). This avoids inventing a UUID.
    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build")
        ActivityThread = autoclass("android.app.ActivityThread")
        SettingsSecure = autoclass("android.provider.Settings$Secure")
        app = ActivityThread.currentApplication()
        if app is not None:
            value = SettingsSecure.getString(app.getContentResolver(), SettingsSecure.ANDROID_ID)
            if value:
                return str(value).replace("@", "_")
    except Exception:
        pass

    for cmd in (("/system/bin/settings", "get", "secure", "android_id"),
                ("settings", "get", "secure", "android_id")):
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2).decode("utf-8", "ignore").strip()
            if out and out.lower() not in ("null", "unknown"):
                return out.replace("@", "_")
        except Exception:
            pass
    return ""


def android_build_info():
    manufacturer = android_prop("ro.product.manufacturer", "")
    model = android_prop("ro.product.model", "")
    sdk = android_prop("ro.build.version.sdk", "")
    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build")
        manufacturer = manufacturer or str(Build.MANUFACTURER)
        model = model or str(Build.MODEL)
        sdk = sdk or str(Build.VERSION.SDK_INT)
    except Exception:
        pass
    return manufacturer.strip(), model.strip(), sdk.strip()


_MANUFACTURER, _MODEL, _ANDROID_SDK = android_build_info()
_MANUFACTURER = os.getenv("DEVICE_MANUFACTURER", "").strip() or _MANUFACTURER
_MODEL = os.getenv("DEVICE_PRODUCT_MODEL", "").strip() or _MODEL
SDK = os.getenv("SDK", "").strip() or _ANDROID_SDK

# Do NOT silently generate a fake device identity. The APK sends the real
# Android ID. If Pydroid cannot access it, the operator can set DEVICE_ID in
# .env after obtaining the value from the same Android device.
DEVICE_ID = os.getenv("DEVICE_ID", "").strip() or android_secure_id()
# Exact fallback from the APK's M9/c.h(): when ANDROID_ID is unavailable,
# it uses the literal prefix "null-" followed by a UUID, then replaces @.
if not DEVICE_ID:
    # APK behavior: when ANDROID_ID is unavailable it creates a UUID and
    # stores it in SharedPreferences, so it stays stable across reconnects.
    _fallback_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".talkin_device_id")
    try:
        if os.path.exists(_fallback_file):
            DEVICE_ID = open(_fallback_file, "r", encoding="utf-8").read().strip()
    except Exception:
        pass
    if not DEVICE_ID:
        DEVICE_ID = "null-" + str(uuid.uuid4()).lower()
        try:
            with open(_fallback_file, "w", encoding="utf-8") as _f:
                _f.write(DEVICE_ID)
        except Exception:
            pass
    print("[DEVICE] ANDROID_ID unavailable; using persistent APK fallback", DEVICE_ID)
_MANUFACTURER = _MANUFACTURER or "Generic"
_MODEL = _MODEL or "Railway"
SDK = SDK or "35"
DEVICE_MODEL = os.getenv("DEVICE_MODEL", "").strip() or (
    "444$" + _MANUFACTURER.replace("@", "-") + "-" + _MODEL.replace("@", "-") + "$" + SDK
)

API_VER = "2"
CLIENT_VER = "1"
AUTH_VER = "444"
AUTH_METHOD = "1"

# Keep these enabled for easy troubleshooting.
DEBUG = os.getenv("DEBUG", "1") == "1"
WS_IDLE_READ_TIMEOUT = float(os.getenv("WS_IDLE_READ_TIMEOUT", "5"))
WS_KEEPALIVE_INTERVAL = float(os.getenv("WS_KEEPALIVE_INTERVAL", "10"))
RAW_DIAGNOSTIC = os.getenv("RAW_DIAGNOSTIC", "1") == "1"
ACK_ROOM_EVENTS = os.getenv("ACK_ROOM_EVENTS", "1") == "1"
AUTO_HELP = os.getenv("AUTO_HELP", "1") == "1"
BANNED_WORDS = {w.strip().lower() for w in os.getenv("BANNED_WORDS", "").split(",") if w.strip()}
AUTO_BAN_WORDS = os.getenv("AUTO_BAN_WORDS", "0") == "1"

# ------------------------- protobuf wire helpers -------------------------

def _varint(n: int) -> bytes:
    n = int(n)
    if n < 0:
        n &= (1 << 64) - 1
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _field_string(num: int, value: str, force: bool = False) -> bytes:
    if value is None:
        value = ""
    raw = str(value).encode("utf-8")
    # APK protobuf classes use presence bits, so forced empty fields are
    # useful for AuthRequest where setters are called even for empty captcha.
    if not raw and not force:
        return b""
    return _varint((num << 3) | 2) + _varint(len(raw)) + raw


def _field_int32(num: int, value: int, force: bool = False) -> bytes:
    value = int(value)
    if value == 0 and not force:
        return b""
    return _varint(num << 3) + _varint(value)


def encode_auth_request(username: str, password: str, captcha_code: str = "", captcha_url: str = "") -> bytes:
    # AuthRequest fields from net.chatp.data.AuthRequest.smali:
    # 1 type, 2 username, 3 password, 4 captchaCode, 5 captchaUrl,
    # 6 sid, 7 sdk, 8 os, 9 ver, 10 clientVer, 11 deviceId,
    # 12 deviceModel, 13 language, 14 method.
    parts = [
        _field_string(1, "login", True),
        _field_string(2, username, True),
        _field_string(3, password, True),
        _field_string(4, captcha_code, True),
        _field_string(5, captcha_url, True),
        _field_string(6, str(uuid.uuid4()), True),
        _field_string(7, SDK, True),
        _field_string(8, "android@" + REFERRER_URL, True),
        _field_string(9, AUTH_VER, True),
        _field_string(10, "2", True),
        _field_string(11, DEVICE_ID, True),
        _field_string(12, DEVICE_MODEL, True),
        _field_string(13, LANGUAGE, True),
        _field_string(14, AUTH_METHOD, True),
    ]
    return b"".join(parts)


def encode_query(action: str, *, type_: str = None, length: str = None,
                 to: str = None, body: str = None, room: str = None,
                 url: str = None, uid: str = None, password: str = None,
                 state: str = None, value: str = None, value1: str = None,
                 int_value: int = None, long_value: int = None,
                 use_bin: int = None, captcha_code: str = None,
                 captcha_url: str = None, id_: str = None,
                 product_id: str = None, order_id: str = None,
                 purchase_time: str = None, purchase_state: str = None,
                 payload: str = None, token: str = None,
                 force_int_value: bool = False) -> bytes:
    # Query fields from net.chatp.data.Query.smali.
    vals = {
        1: action, 2: type_, 3: length, 4: to, 5: body, 6: room,
        7: url, 8: uid, 9: password, 10: state, 11: value, 12: value1,
        16: captcha_code, 17: captcha_url, 18: id_, 19: product_id,
        20: order_id, 21: purchase_time, 22: purchase_state,
        23: payload, 24: token,
    }
    out = bytearray()
    out += _field_string(1, action, True)
    for num in range(2, 25):
        if num in (13, 14, 15):
            continue
        if num in vals and vals[num] is not None:
            out += _field_string(num, vals[num], True)
    if int_value is not None:
        out += _field_int32(13, int_value, force_int_value)
    if long_value is not None:
        out += _varint(14 << 3) + _varint(int(long_value))
    if use_bin is not None:
        out += _field_int32(15, use_bin, True)
    return bytes(out)


def read_varint(data: bytes, pos: int):
    value = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, pos
        shift += 7
        if shift > 70:
            raise ValueError("invalid protobuf varint")
    raise ValueError("truncated protobuf varint")


def decode_message(data: bytes):
    """Generic protobuf decoder; enough for the APK schemas and nested events."""
    fields = defaultdict(list)
    pos = 0
    while pos < len(data):
        key, pos = read_varint(data, pos)
        num, wire = key >> 3, key & 7
        if num == 0:
            break
        if wire == 0:
            value, pos = read_varint(data, pos)
            fields[num].append(value)
        elif wire == 1:
            if pos + 8 > len(data): raise ValueError("truncated fixed64")
            fields[num].append(data[pos:pos+8]); pos += 8
        elif wire == 2:
            length, pos = read_varint(data, pos)
            if pos + length > len(data): raise ValueError("truncated bytes")
            fields[num].append(data[pos:pos+length]); pos += length
        elif wire == 5:
            if pos + 4 > len(data): raise ValueError("truncated fixed32")
            fields[num].append(data[pos:pos+4]); pos += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
    return fields


def as_text(v):
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    return str(v)


def first_text(fields, num, default=""):
    vals = fields.get(num)
    return as_text(vals[0]) if vals else default


def first_int(fields, num, default=0):
    vals = fields.get(num)
    if not vals: return default
    return int(vals[0]) if isinstance(vals[0], int) else default


def decode_auth_result(data: bytes):
    f = decode_message(data)
    # AuthResult: 1 result, 2 userId, 3 photoUrl, 4 photoVersion,
    # 5 id, 6 message, 7 server, 8 method, 9 enablePing, 10 enableRoomAck.
    return {
        "result": first_text(f, 1),
        "user_id": first_text(f, 2),
        "photo_url": first_text(f, 3),
        "photo_version": first_text(f, 4),
        "id": first_text(f, 5),
        "message": first_text(f, 6),
        "server": first_text(f, 7),
        "method": first_text(f, 8),
        "enable_ping": bool(first_int(f, 9)),
        "enable_room_ack": bool(first_int(f, 10)),
    }


def decode_result_message(data: bytes):
    f = decode_message(data)
    result = {
        "handler_id": first_int(f, 1),
        "type": first_text(f, 2),
        "page": first_int(f, 3),
        "uid": first_text(f, 4),
        "value": first_text(f, 5),
        "int_value": first_int(f, 6),
    }
    # ResultMessage nested protobuf fields:
    # 8 StreamEvent, 9 ChatMessage, 10 RoomEvent, 11 users,
    # 12 rooms, 13 CallInfo, 14 RoomAdmin, 15 LoginInfo, 16 sessions.
    if 8 in f:
        result["stream_event"] = decode_generic(f[8][0])
    if 9 in f:
        result["chat_message"] = decode_generic(f[9][0])
    if 10 in f:
        result["room_event"] = decode_generic(f[10][0])
    if 11 in f:
        result["users"] = [decode_generic(x) for x in f[11]]
    if 12 in f:
        result["rooms"] = [decode_generic(x) for x in f[12]]
    if 13 in f:
        result["call_info"] = decode_generic(f[13][0])
    if 14 in f:
        # Keep RoomAdmin field 10 as raw protobuf bytes so occupants_list can
        # decode each UserItem exactly instead of losing the nested structure.
        ra_fields = decode_message(f[14][0])
        ra = decode_generic(f[14][0])
        if 10 in ra_fields:
            ra[10] = list(ra_fields[10])
        result["room_admin"] = ra
    if 15 in f:
        result["login_info"] = decode_generic(f[15][0])
    if 16 in f:
        result["sessions"] = [decode_generic(x) for x in f[16]]
    return result


def decode_generic(data: bytes):
    f = decode_message(data)
    out = {}
    for num, vals in f.items():
        converted = []
        for v in vals:
            if isinstance(v, int):
                converted.append(v)
            elif isinstance(v, bytes):
                try:
                    s = v.decode("utf-8")
                    # Nested protobuf objects are also bytes. Prefer text for
                    # fields that look like UTF-8; otherwise expose raw hex.
                    if any(c == "\x00" for c in s):
                        converted.append(v.hex())
                    else:
                        converted.append(s)
                except UnicodeDecodeError:
                    converted.append(v.hex())
        out[num] = converted[0] if len(converted) == 1 else converted
    return out


# ------------------------- raw WebSocket transport ------------------------
class RawWebSocket:
    """RFC6455 client closely mirroring the supplied Android Y9/v handshake."""
    MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, url, headers, timeout=20, debug=False):
        from urllib.parse import urlsplit
        u = urlsplit(url)
        self.scheme = u.scheme
        self.host = u.hostname
        self.port = u.port or (443 if u.scheme == "wss" else 80)
        self.path = u.path or "/"
        if u.query:
            self.path += "?" + u.query
        self.headers = list(headers or [])
        self.timeout = timeout
        self.debug = debug
        self.sock = None
        self._recvbuf = bytearray()
        self.peer_ip = None
        self.permessage_deflate = False
        self._send_lock = threading.Lock()

    def _connect_android_like(self):
        # Android's Y9/s resolves all addresses before creating the socket.
        # We do the same and keep the TLS hostname as chatp.net for SNI/cert check.
        infos = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        seen = set()
        last = None
        for family, socktype, proto, _canon, sockaddr in infos:
            ip = sockaddr[0]
            if (family, ip, self.port) in seen:
                continue
            seen.add((family, ip, self.port))
            raw = socket.socket(family, socktype, proto)
            raw.settimeout(self.timeout)
            try:
                raw.connect(sockaddr)
                self.peer_ip = ip
                return raw
            except Exception as e:
                last = e
                try: raw.close()
                except Exception: pass
        raise ConnectionError(f"TCP connect failed to {self.host}:{self.port}: {last}")

    def connect(self):
        raw = self._connect_android_like()

        # Android Client obtains the platform default SSLSocketFactory.
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw, server_hostname=self.host)
        self.sock.settimeout(self.timeout)

        # Y9/v: SecureRandom -> 16 bytes -> Base64.
        key = base64.b64encode(os.urandom(16)).decode("ascii")

        # Y9/v builds this base order. Newer TalkinChat builds may use a
        # conventional WebSocket stack, so optional compatibility headers are
        # selected by the caller rather than being hard-coded.
        lines = [
            f"GET {self.path} HTTP/1.1",
            f"Host: {self.host}:{self.port}",
            "Connection: Upgrade",
            "Upgrade: websocket",
            "Sec-WebSocket-Version: 13",
            f"Sec-WebSocket-Key: {key}",
        ]
        lines.extend(self.headers)
        request = "\r\n".join(lines) + "\r\n\r\n"

        if self.debug:
            # Header values contain credentials encoded by the APK protocol.
            # Redact username/password header values in diagnostics.
            shown=[]
            for line in lines:
                low=line.lower()
                if low.startswith("username:") or low.startswith("password:"):
                    shown.append(line.split(":",1)[0] + ": <redacted>")
                else:
                    shown.append(line)
            print("[RAW-WS] peer_ip=", self.peer_ip, flush=True)
            print("[RAW-WS] TLS=", self.sock.version(), "cipher=", self.sock.cipher(), flush=True)
            print("[RAW-WS] handshake:\n" + "\\r\\n\n".join(shown) + "\\r\\n\\r\\n", flush=True)

        self.sock.sendall(request.encode("utf-8"))

        # Read the complete HTTP response header so a 404 can be diagnosed.
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("server closed during WebSocket handshake")
            buf += chunk
            if len(buf) > 65536:
                raise ConnectionError("oversized WebSocket handshake")

        head, self._prefetch = buf.split(b"\r\n\r\n", 1)
        text = head.decode("iso-8859-1", "replace")
        response_lines = text.split("\r\n")
        status = response_lines[0] if response_lines else ""

        if self.debug:
            print("[RAW-WS] response:", flush=True)
            print(text, flush=True)

        if not (" 101 " in status or status.endswith(" 101")):
            # Include headers/body prefix but never echo credential-bearing request headers.
            body_preview = self._prefetch[:512].decode("utf-8", "replace") if self._prefetch else ""
            detail = status
            if body_preview:
                detail += " | body=" + repr(body_preview)
            raise ConnectionError("WebSocket handshake rejected: " + detail)

        h = {}
        for line in response_lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                h[k.strip().lower()] = v.strip()
        ext = h.get("sec-websocket-extensions", "")
        self.permessage_deflate = "permessage-deflate" in ext.lower()
        if self.debug and ext:
            print("[RAW-WS] negotiated extensions:", ext, flush=True)
        expected = base64.b64encode(hashlib.sha1((key + self.MAGIC).encode("ascii")).digest()).decode("ascii")
        if h.get("sec-websocket-accept") != expected:
            raise ConnectionError("invalid Sec-WebSocket-Accept")
        self._recvbuf = bytearray(self._prefetch)

    def _recv_exact(self, n):
        while len(self._recvbuf) < n:
            chunk = self.sock.recv(max(4096, n-len(self._recvbuf)))
            if not chunk:
                raise ConnectionError("socket closed")
            self._recvbuf.extend(chunk)
        out = bytes(self._recvbuf[:n]); del self._recvbuf[:n]
        return out

    def send_binary(self, payload):
        payload = bytes(payload)
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            hdr = bytes([0x82, 0x80 | n])
        elif n <= 0xffff:
            hdr = bytes([0x82, 0x80 | 126]) + struct.pack('!H', n)
        else:
            hdr = bytes([0x82, 0x80 | 127]) + struct.pack('!Q', n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            if not self.sock:
                raise ConnectionError("socket is not connected")
            self.sock.sendall(hdr + mask + masked)

    def send_control(self, opcode, payload=b''):
        payload = bytes(payload); mask = os.urandom(4)
        if len(payload) > 125: raise ValueError('control frame too large')
        hdr = bytes([0x80 | opcode, 0x80 | len(payload)])
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            if not self.sock:
                raise ConnectionError("socket is not connected")
            self.sock.sendall(hdr + mask + masked)

    def recv(self):
        b1, b2 = self._recv_exact(2)
        rsv1 = bool(b1 & 0x40)
        opcode = b1 & 0x0f; masked = bool(b2 & 0x80); n = b2 & 0x7f
        if n == 126: n = struct.unpack('!H', self._recv_exact(2))[0]
        elif n == 127: n = struct.unpack('!Q', self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b''
        data = self._recv_exact(n)
        if masked: data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if rsv1 and self.permessage_deflate and opcode in (0x1, 0x2, 0x0):
            import zlib
            try:
                data = zlib.decompress(data + b"\\x00\\x00\\xff\\xff", -zlib.MAX_WBITS)
            except zlib.error:
                pass
        if opcode == 0x8:
            code = None; reason = ''
            if len(data) >= 2:
                try:
                    code = struct.unpack('!H', data[:2])[0]
                    reason = data[2:].decode('utf-8', 'replace')
                except Exception:
                    pass
            return ('close', {'code': code, 'reason': reason, 'raw': data})
        if opcode == 0x9:
            self.send_control(0xA, data); return ('ping', data)
        if opcode == 0xA: return ('pong', data)
        if opcode == 0x1: return ('text', data.decode('utf-8', 'replace'))
        if opcode == 0x2: return ('binary', data)
        return ('other', data)

    def close(self):
        try:
            if self.sock: self.send_control(0x8, b'')
        except Exception: pass
        try:
            if self.sock: self.sock.close()
        except Exception: pass
        self.sock = None

# ------------------------------ Database ----------------------------------

class DatabaseBridge:
    """Read the same room_members/profiles data used by the web app.

    The supplied app source explicitly reads room_members(user_id, rank,
    joined_at, is_present) and then resolves those IDs through profiles.
    """
    def __init__(self, log):
        self.log = log
        self.client = None
        self.url = os.getenv("SUPABASE_URL", "").strip()
        self.key = os.getenv("SUPABASE_KEY", "").strip()
        self.email = os.getenv("SUPABASE_EMAIL", "").strip()
        self.password = os.getenv("SUPABASE_PASSWORD", "")
        self.last_error = ""
        self.last_room_id = ""
        self.last_member_count = 0
        self.last_profile_count = 0
        cfg_path = Path(os.getenv("DB_CONFIG_PATH", str(Path(__file__).resolve().parent / "config.json")))
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                self.url = self.url or str(cfg.get("supabase_url", "")).strip()
                self.key = self.key or str(cfg.get("supabase_key", "")).strip()
                self.email = self.email or str(cfg.get("supabase_email", cfg.get("email", ""))).strip()
                self.password = self.password or str(cfg.get("supabase_password", cfg.get("password", "")))
            except Exception as e:
                self.log("[DB] config read failed:", repr(e))
        if not create_client:
            self.log("[DB] Supabase library غير مثبتة/غير قابلة للاستيراد")
        elif not self.url or not self.key:
            self.log("[DB] Supabase client غير متاح: SUPABASE_URL/SUPABASE_KEY مفقودان")
        else:
            try:
                if self.key.startswith("sb_publishable_"):
                    self.client = create_client(self.url, "a.b.c")
                    self.client.supabase_key = self.key
                    self.client.options.headers["apiKey"] = self.key
                    self.client.options.headers.pop("Authorization", None)
                else:
                    self.client = create_client(self.url, self.key)
                self.log("[DB] Supabase client ready")
            except Exception as e:
                self.log("[DB] client init failed:", repr(e))

    def sign_in(self):
        if not self.client or not self.email or not self.password:
            return False
        try:
            res = self.client.auth.sign_in_with_password({"email": self.email, "password": self.password})
            user = getattr(res, "user", None)
            self.log("[DB] Supabase auth:", "OK" if user else "FAILED")
            if user:
                self.log("[DB] authenticated Supabase user ready for native invites")
            return bool(user)
        except Exception as e:
            self.log("[DB] Supabase auth failed:", repr(e))
            return False

    def room_id(self, room_name):
        if not self.client: return None
        name = str(room_name or "").strip()
        try:
            r = self.client.table("rooms").select("id,name").eq("name", name).limit(1).execute()
            rows = getattr(r, "data", None) or []
            if rows:
                rid = str(rows[0].get("id"))
                self.last_room_id = rid
                return rid
        except Exception as e:
            self.last_error = str(e)
            self.log("[DB] room lookup failed:", repr(e))
        return None

    def room_users(self, room_name):
        if not self.client: return []
        rid = self.room_id(room_name)
        if not rid: return []
        try:
            r = self.client.table("room_members").select("user_id, rank, joined_at, is_present").eq("room_id", rid).execute()
            members = getattr(r, "data", None) or []
            self.last_member_count = len(members)
            ids = []
            for row in members:
                uid = row.get("user_id")
                if uid and str(uid) not in ids: ids.append(str(uid))
            if not ids: return []
            out=[]
            for i in range(0, len(ids), 100):
                batch=ids[i:i+100]
                pr=self.client.table("profiles").select("id, username").in_("id", batch).execute()
                for row in (getattr(pr,"data",None) or []):
                    u=str(row.get("username") or "").strip()
                    if u: out.append({"username":u,"user_id":str(row.get("id") or "")})
            seen=set(); final=[]
            for u in out:
                k=u["username"].casefold()
                if k not in seen: seen.add(k); final.append(u)
            self.last_profile_count = len(final)
            self.log(f"[DB] room_members={len(members)} profiles={len(final)} room_id={rid}")
            return final
        except Exception as e:
            self.last_error = str(e)
            self.log("[DB] room_members query failed:", repr(e))
            return []

# ------------------------------ Bot --------------------------------------

class TalkinBot:
    def __init__(self):
        self.ws = None
        self.stop_event = threading.Event()
        self.http = requests.Session()
        self.port = DEFAULT_PORT
        self.room = GROUP_TO_JOIN
        self.auth = None
        self.last_error = None
        self.banned_words = set()
        self.last_messages = defaultdict(list)
        # Live room membership cache: username -> role.  This is updated by
        # occupants_list and by user_joined/user_left room events.
        self.room_users = defaultdict(dict)
        self.last_joined_room = None
        self.invite_pending = False
        self.invite_room = ""
        self.invite_sent = set()
        self.invite_thread = None
        self.invite_lock = threading.Lock()
        self.invite_message_template = "{sender} يدعوك للغرفة {room}"
        self.known_rooms = set()
        # Persistent points ledger. The configured master has unlimited points
        # and is never stored in the ledger. All other balances are integers.
        self.points_file = Path(os.getenv("POINTS_FILE", str(Path(__file__).resolve().parent / "points.json")))
        self.points_lock = threading.Lock()
        self.points = self._load_points()
        self.banned_words = set(BANNED_WORDS)
        self.db = DatabaseBridge(self.log)
        self.db.sign_in()
        self.media_server = None
        try:
            self.media_server = start_media_server(int(os.getenv("PORT", "8080")))
        except Exception as e:
            self.log("[MEDIA] server failed:", repr(e))

    def _load_points(self):
        try:
            if self.points_file.exists():
                data = json.loads(self.points_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): max(0, int(v)) for k, v in data.items()}
        except Exception as e:
            print("[POINTS] load failed:", repr(e), flush=True)
        return {}

    def _save_points(self):
        try:
            self.points_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.points_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.points, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.points_file)
        except Exception as e:
            print("[POINTS] save failed:", repr(e), flush=True)

    def is_master(self, username):
        return bool(BOT_MASTER and str(username or "").strip().casefold() == BOT_MASTER.casefold())

    def points_balance(self, username):
        if self.is_master(username):
            return None  # unlimited
        with self.points_lock:
            return int(self.points.get(str(username).strip(), 0))

    def transfer_points(self, sender, receiver, amount):
        sender = str(sender or "").strip().lstrip("@")
        receiver = str(receiver or "").strip().lstrip("@")
        amount = int(amount)
        if not sender or not receiver:
            raise ValueError("اسم المستخدم غير صحيح")
        if amount <= 0:
            raise ValueError("كمية النقاط يجب أن تكون أكبر من صفر")
        if sender.casefold() == receiver.casefold():
            raise ValueError("لا يمكن تحويل النقاط إلى نفسك")
        with self.points_lock:
            if not self.is_master(sender):
                balance = int(self.points.get(sender, 0))
                if balance < amount:
                    raise ValueError(f"رصيدك غير كافٍ. رصيدك: {balance:,} نقطة")
                self.points[sender] = balance - amount
            if not self.is_master(receiver):
                self.points[receiver] = int(self.points.get(receiver, 0)) + amount
            self._save_points()
        return self.points_balance(sender), self.points_balance(receiver)

    def points_text(self, username):
        bal = self.points_balance(username)
        return "♾️ نقاطك: غير محدودة" if bal is None else f"💰 نقاطك: {bal:,}"

    def log(self, *args):
        if DEBUG:
            print(*args, flush=True)

    def authenticate(self):
        body = encode_auth_request(BOT_ID, BOT_PWD)
        url = API_BASE_URL + "auth_new"
        self.log("[AUTH] POST", url)
        r = self.http.post(
            url,
            data=body,
            headers={"Content-Type": "application/octet-stream", "User-Agent": "Talkinchat/1.0 (Android 12; net.chatp)"},
            timeout=15,
        )
        r.raise_for_status()
        self.auth = decode_auth_result(r.content)
        self.log("[AUTH] result=", self.auth["result"], "user_id=", self.auth["user_id"], "server=", self.auth["server"])
        if self.auth["message"]:
            self.log("[AUTH] message=", self.auth["message"])
        self.auth_server = self.auth["server"] if self.auth["server"].isdigit() else ""
        # The APK stores AuthResult.id as the shared-preference captcha_id,
        # and M9/c.c() uses that value in the default `b` handshake header.
        # Using the hard-coded default `0` causes the server to accept the
        # HTTP/WebSocket upgrade but then close with `require_login`.
        if self.auth.get("id"):
            self.captcha_id = self.auth["id"]
        else:
            self.captcha_id = os.getenv("CAPTCHA_ID", "0")
        self.photo_version = self.auth.get("photo_version") or os.getenv("PHOTO_VERSION", "0")
        self.roster_version = os.getenv("ROSTER_VERSION", "0")
        self.log("[AUTH] session id/captcha_id received; using it for WS b header")
        self.port = DEFAULT_PORT
        if self.auth["result"].lower() not in ("ok", "success", "true", "1"):
            raise RuntimeError("Authentication rejected: " + (self.auth["message"] or self.auth["result"]))
        return self.auth

    @staticmethod
    def b64(value: str) -> str:
        # Android Base64.encode(bytes, Base64.NO_WRAP) == standard Base64 without line breaks.
        return base64.b64encode((value or "").encode("utf-8")).decode("ascii")

    def app_ws_headers(self):
        """Use the default TalkinChat 5.8.3 Client branch: a single `b` header.

        Client.smali checks SharedPreferences `default/m` with default `n`.
        On the normal/default path it calls M9/c.c(), which builds `b` from:
        captcha_id @ android_id @ device_model @ android@language@photo_version@roster_version
        and Base64.NO_WRAP encodes the whole string.
        """
        user_id = str((self.auth or {}).get("user_id") or os.getenv("USER_ID", "0"))
        captcha_id = getattr(self, "captcha_id", os.getenv("CAPTCHA_ID", "0"))
        photo_version = getattr(self, "photo_version", os.getenv("PHOTO_VERSION", "0"))
        roster_version = getattr(self, "roster_version", os.getenv("ROSTER_VERSION", "0"))

        raw = (
            captcha_id + "@" +
            DEVICE_ID + "@" +
            DEVICE_MODEL + "@android@" +
            LANGUAGE + "@" +
            photo_version + "@" +
            roster_version
        )
        encoded = self.b64(raw)
        if DEBUG:
            self.log("[WS] b(decoded)=", raw)
            self.log("[WS] b(base64)=", encoded)
            self.log("[WS] b(user_id)=", user_id)
        return ["b: " + encoded]

    def websocket_url(self, path=None):
        # Authentication is separate via auth_new. Keep the path configurable
        # because the service has returned 404 for the old /server endpoint
        # when its realtime gateway is moved.
        return "wss://%s:%s%s" % (
            getattr(self, "ws_host", HOST), self.port,
            path if path is not None else getattr(self, "ws_path", WS_PATHS[0]),
        )

    def send_query(self, payload: bytes):
        if not self.ws:
            raise RuntimeError("WebSocket is not connected")
        self.ws.send_binary(payload)

    def join_room(self, room: str):
        self.log("[ROOM] joining", room)
        # APK's room_join sets room and explicitly sets intValue=0.
        self.send_query(encode_query("room_join", room=room, int_value=0, force_int_value=True))

    def send_room_text(self, room: str, text: str):
        self.send_query(encode_query("room_message", type_="text", room=room, body=text))

    def send_room_media(self, room: str, media_type: str, url: str, text: str = "", duration_ms: int = 0):
        self.send_query(encode_query("room_message", type_=media_type, room=room, body=text, url=url, length=str(int(duration_ms or 0))))

    def send_admin(self, room: str, target: str, operation: str):
        # Exact command forms observed in the APK.
        if operation == "kick":
            return self.send_query(encode_query("room_admin", type_="kick", room=room, to=target, value="none"))
        if operation == "ban":
            return self.send_query(encode_query("room_admin", type_="ban_ip", room=room, to=target, value="outcast"))
        role_map = {
            "outcast": "outcast",
            "admin": "admin",
            "member": "member",
            "owner": "owner",
            "none": "none",
        }
        if operation in role_map:
            return self.send_query(encode_query("room_admin", type_="change_role", room=room, to=target, value=role_map[operation]))
        raise ValueError("Unknown admin operation: " + operation)

    def ack(self, uid: str):
        if uid:
            self.send_query(encode_query("ack_msg", uid=uid))

    def send_private_text(self, username: str, text: str):
        """Send one normal TalkinChat private text message."""
        username = str(username or "").strip()
        if not username or username == BOT_ID:
            return False
        self.send_query(encode_query("chat_message", type_="text", to=username, body=text))
        return True

    def report_master_error(self, source: str, exc: Exception):
        """Send the real exception to the configured master privately.
        The room only receives the short user-friendly failure message.
        """
        if not BOT_MASTER:
            return
        try:
            detail = traceback.format_exc().strip()
            if not detail or detail == "NoneType: None":
                detail = repr(exc)
            # Keep private diagnostics readable and bounded.
            if len(detail) > 3500:
                detail = detail[-3500:]
            text = (
                f"🚨 خطأ فعلي في البوت\n"
                f"📍 القسم: {source}\n"
                f"⚠️ النوع: {type(exc).__name__}\n"
                f"📝 الخطأ: {exc!s}\n"
                f"```\n{detail}\n```"
            )
            self.send_private_text(BOT_MASTER, text)
        except Exception as report_exc:
            self.log("[ERROR-REPORT] failed:", repr(report_exc))

    def request_occupants(self, room: str = ""):
        """Load users from ALL rooms currently joined by the bot.

        The room argument is only the command-context room: it is used in the
        invitation text. The source roster is collected from every room in
        self.known_rooms, so joining another room never replaces old rooms.
        """
        with self.invite_lock:
            if self.invite_pending:
                self.send_private_text(BOT_MASTER, "⏳ ما زلت أجمع معلومات الغرف، انتظر حتى تكتمل العملية.")
                return
            self.invite_pending = True
            self.invite_room = str(room or self.room or "").strip()
            self.invite_sent.clear()

        command_room = self.invite_room
        active_rooms = []
        for r in list(self.known_rooms):
            r = str(r).strip()
            if r and r not in active_rooms:
                active_rooms.append(r)
        if self.room and self.room not in active_rooms:
            active_rooms.insert(0, self.room)

        self.log("[INV] loading users from ALL active rooms:", active_rooms)
        try:
            self.send_private_text(
                BOT_MASTER,
                f"⏳ جاري جمع جميع المستخدمين من {len(active_rooms)} غرفة...\n"
                f"📌 نص الدعوة سيكون باسم الغرفة التي نُفّذ فيها inv: {command_room}"
            )
        except Exception as e:
            self.log("[INV] private progress message failed:", repr(e))

        # Collect the persistent roster for every room. This includes members
        # who are currently offline, not just the live occupants.
        all_users = []
        seen = set()
        room_counts = {}
        for source_room in active_rooms:
            db_users = self.db.room_users(source_room)
            room_counts[source_room] = len(db_users)
            for u in db_users or []:
                username = str(u.get("username") or "").strip() if isinstance(u, dict) else ""
                if not username or username == BOT_ID:
                    continue
                key = username.casefold()
                if key in seen:
                    continue
                seen.add(key)
                all_users.append(username)

        if all_users:
            self.log(f"[INV] ALL rooms loaded: rooms={len(active_rooms)} unique_users={len(all_users)} counts={room_counts}")
            self.process_occupants_for_invite({
                "db_users": [{"username": u} for u in all_users],
                "source_rooms": active_rooms,
            })
            return

        # If DB is unavailable, request occupants_list from every active room.
        # Results are accumulated by room until all responses arrive.
        self._inv_expected_rooms = set(active_rooms)
        self._inv_live_users = []
        self._inv_live_seen = set()
        self._inv_command_room = command_room
        if not active_rooms:
            with self.invite_lock:
                self.invite_pending = False
            self.send_private_text(BOT_MASTER, "⚠️ لا توجد غرف نشطة حالياً. استخدم: دخول اسم_الغرفة")
            return
        for source_room in active_rooms:
            try:
                self.send_query(encode_query(
                    "room_admin", type_="occupants_list", room=source_room,
                    to=BOT_ID, value="none"
                ))
            except Exception as e:
                self.log("[INV] occupants request failed", source_room, repr(e))
                self._inv_expected_rooms.discard(source_room)
        if not self._inv_expected_rooms:
            with self.invite_lock:
                self.invite_pending = False

    def send_native_system_invite(self, username: str, room: str):
        """Send the platform's native room invitation through its Supabase RPC.

        The supplied web/admin source calls room_invite_username with:
            {"_room": <room UUID>, "_username": <username>}
        This is different from chat_message: it creates the same invitation flow
        used by the official system, subject to the bot's authenticated account
        having permission to invite in that room.
        """
        if not self.db.client:
            return False, "Supabase client غير متاح"
        rid = self.db.room_id(room)
        if not rid:
            return False, "لم أجد room_id للغرفة في قاعدة البيانات"
        try:
            res = self.db.client.rpc("room_invite_username", {"_room": rid, "_username": str(username).strip()}).execute()
            err = getattr(res, "error", None)
            data = getattr(res, "data", None)
            if err:
                detail = str(getattr(err, "message", err))
                self.log("[INV] RPC error:", username, detail)
                return False, detail
            self.log("[INV] RPC OK:", username, "data=", repr(data)[:300])
            return True, "ok"
        except Exception as e:
            detail = repr(e)
            self.log("[INV] RPC exception:", username, detail)
            return False, detail

    def send_private_invite(self, username: str, room: str):
        """Send a NORMAL private chat invitation, not a system/RPC invitation.

        The room name is always the exact room in which the `inv` command was
        executed (or the room explicitly supplied to a master private `inv`
        command). This keeps the invitation text tied to the command room.
        """
        username = str(username or "").strip()
        room = str(room or "").strip()
        if not username or username == BOT_ID or not room:
            return False
        with self.invite_lock:
            if username in self.invite_sent:
                return False

        # IMPORTANT: normal TalkinChat private message, deliberately NOT
        # room_invite_username / native system invitation.
        text = self.invite_message_template
        try:
            text = text.format(sender=INVITE_SENDER_NAME, room=room, username=username)
        except Exception:
            text = f"{INVITE_SENDER_NAME} يدعوك للغرفة {room}"
        self.send_query(encode_query("chat_message", type_="text", to=username, body=text))

        with self.invite_lock:
            self.invite_sent.add(username)
        self.log("[INV] normal private invite sent:", username, "room=", room)
        return True

    def _users_from_room_admin(self, room_admin):
        """Extract UserItem records from RoomAdmin field 10.

        UserItem fields in the APK: 1=username, 2=user_id, 3=photo,
        4=status, 5=online, 6=role.  The old decoder converted nested
        protobuf bytes to strings, so V12 keeps the bytes and decodes them
        here before any invitation or role grouping is done.
        """
        if not isinstance(room_admin, dict):
            return []
        raw = room_admin.get(10) or []
        if not isinstance(raw, list):
            raw = [raw]
        users = []
        for item in raw:
            try:
                if isinstance(item, bytes):
                    uf = decode_message(item)
                elif isinstance(item, dict):
                    uf = item
                else:
                    continue
                username = first_text(uf, 1).strip()
                role = first_text(uf, 6).strip().lower()
                user_id = first_text(uf, 2).strip()
                online = first_text(uf, 5).strip()
                if username and username != BOT_ID:
                    users.append({"username": username, "role": role or "none",
                                  "user_id": user_id, "online": online})
            except Exception as e:
                self.log("[INV] UserItem decode failed:", repr(e))
        # De-duplicate by username while preserving server order.
        out = []
        seen = set()
        for u in users:
            k = u["username"].casefold()
            if k not in seen:
                seen.add(k)
                out.append(u)
        return out

    def _usernames_from_room_admin(self, room_admin):
        return [u["username"] for u in self._users_from_room_admin(room_admin)]

    def _finish_invites(self, room, usernames):
        """Send invitations in a worker so the main receive loop stays alive."""
        count = 0
        try:
            for username in usernames:
                try:
                    if self.send_private_invite(username, room):
                        count += 1
                    # Small pacing gap, but never blocks the WebSocket reader.
                    time.sleep(0.08)
                except Exception as e:
                    self.log("[INV] failed for", username, repr(e))

            self.log(f"[INV] occupants loaded: {len(usernames)}, invitations sent: {count}")
            try:
                if count == 0:
                    self.send_private_text(BOT_MASTER,
                        f"⚠️ لم تُرسل أي دعوة نظام. DB client={'نعم' if self.db.client else 'لا'} | "
                        f"Supabase room_id={self.db.last_room_id or 'غير موجود'} | "
                        f"room_members={self.db.last_member_count} | profiles={self.db.last_profile_count} | "
                        f"آخر خطأ={self.db.last_error or 'راجع سجل Pydroid'}")
            except Exception:
                pass
            try:
                self.send_private_text(
                    BOT_MASTER,
                    f"✅ تم جمع معلومات الغرفة. عدد المستخدمين: {len(usernames)}\n"
                    f"📨 تم إرسال الدعوة العادية على الخاص إلى: {count} مستخدم."
                )
            except Exception as e:
                self.log("[INV] final private result failed:", repr(e))
        finally:
            with self.invite_lock:
                self.invite_pending = False

    def process_occupants_for_invite(self, result):
        if not self.invite_pending:
            return
        room = self.invite_room or self.room

        # Fallback live responses are tagged by the room they came from.
        # Accumulate all room responses before sending the final invitation batch.
        source_room = str(result.get("_occupants_room") or "").strip()
        if source_room and hasattr(self, "_inv_expected_rooms"):
            for u in self._users_from_room_admin(result.get("room_admin") or {}):
                username = str(u.get("username") or "").strip()
                if username and username != BOT_ID and username.casefold() not in getattr(self, "_inv_live_seen", set()):
                    self._inv_live_seen.add(username.casefold())
                    self._inv_live_users.append(username)
            self._inv_expected_rooms.discard(source_room)
            if self._inv_expected_rooms:
                return
            result = {"db_users": [{"username": u} for u in self._inv_live_users]}

        users_info = []
        for user in (result.get("db_users") or []):
            if isinstance(user, dict):
                username = str(user.get("username") or "").strip()
                if username and username != BOT_ID:
                    users_info.append({"username": username, "role": "none", "user_id": str(user.get("user_id") or "")})

        # Some server builds return ResultMessage.users directly.
        for user in (result.get("users") or []):
            if not isinstance(user, dict):
                continue
            username = str(user.get(1, "") or "").strip()
            role = str(user.get(6, "") or "none").strip().lower()
            if username and username != BOT_ID:
                users_info.append({"username": username, "role": role or "none"})

        # Actual occupants_list response: RoomAdmin field 10 contains the
        # repeated UserItem protobuf messages.
        if not users_info and result.get("room_admin"):
            users_info = self._users_from_room_admin(result["room_admin"])

        # Cache the complete room list, including role categories.
        if users_info:
            self.room_users[room] = {u["username"]: u.get("role", "none") for u in users_info}

        if not users_info:
            self.log("[INV] occupants response received but no usernames decoded")
            try:
                self.send_private_text(BOT_MASTER, "⚠️ وصلت بيانات إعدادات الغرفة لكن لم أستطع استخراج أسماء المستخدمين.")
            except Exception:
                pass
            with self.invite_lock:
                self.invite_pending = False
            return

        # Categorize exactly as the room settings list does.
        owners = [u["username"] for u in users_info if u.get("role") == "owner"]
        admins = [u["username"] for u in users_info if u.get("role") == "admin"]
        members = [u["username"] for u in users_info if u.get("role") not in ("owner", "admin")]
        self.log(f"[INV] room={room} total={len(users_info)} owners={len(owners)} admins={len(admins)} members={len(members)}")

        # Master gets the progress/result privately; no public room spam.
        try:
            self.send_private_text(
                BOT_MASTER,
                f"📋 تم تحميل إعدادات الغرفة. الكل: {len(users_info)} | المالكين: {len(owners)} | المشرفين: {len(admins)} | الأعضاء: {len(members)}"
            )
        except Exception as e:
            self.log("[INV] role summary failed:", repr(e))

        self.invite_thread = threading.Thread(
            target=self._finish_invites,
            args=(room, [u["username"] for u in users_info]),
            name="talkin-invites",
            daemon=True,
        )
        self.invite_thread.start()

    def handle_room_event(self, result):
        event = result.get("room_event") or {}
        event_type = str(event.get(1, ""))
        frm = str(event.get(2, ""))
        to = str(event.get(3, ""))
        body = str(event.get(6, ""))
        room = str(event.get(13, self.room))
        if room and room != BOT_MASTER:
            self.known_rooms.add(room)
        event_id = str(event.get(41, ""))
        username = str(event.get(22, "") or "").strip()
        role = str(event.get(8, "") or "").strip().lower()
        count = str(event.get(23, "") or "").strip()
        reconnected = str(event.get(24, "") or "").strip()
        self.log(f"[EVENT] type={event_type} from={frm} user={username!r} room={room} role={role!r} count={count!r} body={body!r}")

        # Keep the live membership state in sync.  The APK itself uses these
        # exact event names and RoomEvent fields.
        if event_type == "user_joined" and username:
            self.room_users[room][username] = role or "none"
            self.last_joined_room = room
            self.log(f"[ROOM] user joined: {username} role={role or 'none'} count={count} reconnected={reconnected}")
        elif event_type == "user_left" and username:
            self.room_users[room].pop(username, None)
            self.log(f"[ROOM] user left: {username} count={count}")
        elif event_type in ("you_joined", "you_rejoined"):
            self.last_joined_room = room
            self.log(f"[ROOM] BOT is in room: {room} event={event_type}")
        elif event_type in ("room_full_rejoin", "room_unauthorized_rejoin", "room_wrong_password_rejoin", "room_needs_captcha_rejoin", "room_needs_password_rejoin", "room_membership_required_rejoin"):
            # These are server-side rejoin instructions, not a socket failure.
            # Rejoin once, without tearing down the WebSocket.
            self.log(f"[ROOM] server requested rejoin: {event_type}")
            try:
                self.join_room(room)
            except Exception as e:
                self.log("[ROOM] rejoin request failed:", repr(e))

        if ACK_ROOM_EVENTS and result.get("uid"):
            try:
                self.ack(result["uid"])
            except Exception as e:
                self.log("[ACK] failed:", e)

        if event_type != "text" or not body:
            return
        if frm == BOT_ID:
            return

        # Keep a small per-room message history for diagnostics.
        self.last_messages[room].append((frm, body, event_id))
        self.last_messages[room] = self.last_messages[room][-50:]

        # Points commands.
        # sa@اسم_المستخدم@كمية
        raw_body = body.strip()
        if raw_body.casefold().startswith("sa@"):
            parts_sa = raw_body.split("@")
            if len(parts_sa) != 3 or not parts_sa[1].strip() or not parts_sa[2].strip():
                self.send_room_text(room, "❌ الاستخدام الصحيح: sa@اسم_المستخدم@كمية_النقاط")
                return
            receiver = parts_sa[1].strip().lstrip("@")
            try:
                amount = int(parts_sa[2].strip().replace(",", ""))
                sender_balance, receiver_balance = self.transfer_points(frm, receiver, amount)
                sender_after = "♾️ غير محدودة" if sender_balance is None else f"{sender_balance:,}"
                receiver_after = "♾️ غير محدودة" if receiver_balance is None else f"{receiver_balance:,}"
                self.send_room_text(room, f"✅ تم تحويل {amount:,} نقطة من @{frm} إلى @{receiver}\n💰 رصيد المرسل: {sender_after}\n💰 رصيد المستلم: {receiver_after}")
            except Exception as e:
                self.send_room_text(room, f"❌ تعذر تحويل النقاط: {e}")
            return
        if raw_body.casefold() in ("نقاطي", "رصيدي", "points", "balance"):
            self.send_room_text(room, self.points_text(frm))
            return

        # Music and gifts: available to room members.
        low = body.strip().lower()
        try:
            if low in ("الهدايا", "gifts", "gv"):
                self.send_room_text(room, gifts_catalog())
                return
            if low.startswith("اغنية ") or low.startswith("أغنية ") or low.startswith("تشغيل ") or low.startswith("music "):
                query = body.split(None, 1)[1].strip()
                self.send_room_text(room, "⏳ جاري تجهيز الأغنية…")
                track = search_download_youtube(query)
                url = music_url(track["path"])
                self.send_room_text(room, f"🎵 {track['title']}\n🎤 {track['artist']}\n👤 الطلب: @{frm}\n🏠 الغرفة: {room}")
                self.send_room_media(room, "voice", url, f"▶️ {track['title']}", track["duration_ms"])
                return
            if body.strip().lower().startswith("gv@"):
                parts = body.strip().split("@")
                gid = parts[1].strip() if len(parts)>1 else ""
                receiver = parts[2].strip().lstrip("@") if len(parts)>2 else ""
                if gid not in GIFTS:
                    self.send_room_text(room, "❌ رقم الهدية غير صحيح. أرسل gv لرؤية الهدايا.")
                    return
                if not receiver:
                    self.send_room_text(room, "❌ استخدم: gv@رقم_الهدية@اسم_المستخدم")
                    return
                path=gift_image(gid); url=gift_url(path); emoji,name=GIFTS[gid]
                self.send_room_text(room, f"🎁 @{frm} أرسل {emoji} {name} إلى @{receiver}")
                self.send_room_media(room, "image", url, f"{emoji} {name} | من @{frm} إلى @{receiver}")
                return
        except Exception as e:
            self.log("[MEDIA] command failed:", repr(e))
            self.report_master_error("الأغاني والهدايا", e)
            self.send_room_text(room, "❌ تعذر تنفيذ الطلب حالياً. تم إرسال الخطأ الفعلي للماستر.")
            return

        # Master-only administrative commands.
        if BOT_MASTER and frm == BOT_MASTER:
            parts = body.strip().split()
            if parts:
                cmd = parts[0].lower()
                target = parts[1].lstrip("@").strip() if len(parts) >= 2 else ""
                try:
                    if cmd in ("a@", "admin") and target:
                        self.send_admin(room, target, "admin")
                    elif cmd in ("o@", "owner") and target:
                        self.send_admin(room, target, "owner")
                    elif cmd in ("k@", "kick") and target:
                        self.send_admin(room, target, "kick")
                    elif cmd in ("b@", "ban") and target:
                        self.send_admin(room, target, "ban")
                    elif cmd in ("u@", "unban") and target:
                        self.send_admin(room, target, "member")
                    elif cmd in ("دخول", "join", "ادخل", "enter") and target:
                        # Master can command the bot from private chat: "دخول اسم الغرفة".
                        # Joining is done on the existing WebSocket; no reconnect is needed.
                        # Keep every previously joined room. room_join is sent
                        # for the new room without replacing the current room.
                        self.join_room(target)
                        self.known_rooms.add(target)
                        self.send_private_text(BOT_MASTER, f"✅ دخلت الغرفة: {target} | الغرف الحالية: {len(self.known_rooms)}")
                    elif cmd in ("invmsg", "رسالةدعوة"):
                        template = body.split(None, 1)[1].strip() if len(parts) >= 2 else "{sender} يدعوك للغرفة {room}"
                        self.invite_message_template = template
                        self.send_private_text(BOT_MASTER, f"✅ تم تغيير نص الدعوة إلى: {template}")
                    elif cmd in ("inv", "دعوات", "invite"):
                        # In a room: `inv` always uses THIS room's name in the invitation.
                        # From private master chat: `inv اسم_الغرفة` targets that explicit room.
                        target_room = target if target else room
                        if target_room and target_room != BOT_MASTER:
                            self.request_occupants(target_room)
                            self.send_private_text(BOT_MASTER, f"📨 بدأت دعوات جميع الغرف النشطة. اسم الدعوة: {target_room}")
                    elif cmd in ("say", "قل") and len(parts) >= 2:
                        self.send_room_text(room, body.split(None, 1)[1])
                    elif cmd in ("help", "مساعدة") and AUTO_HELP:
                        self.send_room_text(room, "أوامر البوت: k@ اسم للطرد، b@ اسم للحظر، a@ اسم مشرف، o@ اسم مالك، inv لدعوة مستخدمي الغرفة، say النص")
                    else:
                        return
                    self.log("[ADMIN/MASTER]", cmd, target)
                    if cmd in ("k@", "kick", "b@", "ban") and target:
                        try:
                            action_ar = "الطرد" if cmd in ("k@", "kick") else "الحظر"
                            self.send_private_text(BOT_MASTER, f"✅ تم إرسال أمر {action_ar} الفعلي إلى @{target} في الغرفة {room}.")
                        except Exception as e2:
                            self.log("[ADMIN] confirmation failed:", repr(e2))
                except Exception as e:
                    self.log("[ADMIN] failed:", e)
            return

        # Optional automatic word filter. It uses the same room ban operation
        # already implemented for manual `b@` commands. Enable explicitly in .env.
        if AUTO_BAN_WORDS and self.banned_words:
            low = body.casefold()
            hit = next((w for w in self.banned_words if w.casefold() in low), None)
            if hit:
                try:
                    self.send_admin(room, frm, "ban")
                    self.log("[WORD-FILTER] banned", frm, "word=", hit)
                except Exception as e:
                    self.log("[WORD-FILTER] failed:", repr(e))
                return

        if body.lower().strip() in ("!help", "مساعدة") and AUTO_HELP:
            self.send_room_text(room, "أوامر البوت: k@ اسم، b@ اسم، a@ اسم، o@ اسم، inv لدعوة مستخدمي الغرفة")

    def on_message(self, ws, message):
        try:
            if isinstance(message, str):
                self.log("[WS] unexpected text frame:", message[:300])
                return
            result = decode_result_message(message)
            if DEBUG:
                self.log("[WS] handler=", result.get("handler_id"), "type=", result.get("type"), "uid=", result.get("uid"))
            if "room_event" in result:
                self.handle_room_event(result)
            if result.get("users") or result.get("room_admin"):
                self.process_occupants_for_invite(result)
            if result.get("stream_event"):
                self.log("[STREAM]", result["stream_event"])
            if result.get("room_admin"):
                self.log("[ROOM_ADMIN]", result["room_admin"])
            if result.get("chat_message"):
                self.log("[CHAT_MESSAGE]", result["chat_message"])
                # Private master commands are also accepted as ChatMessage frames.
                cm = result["chat_message"]
                try:
                    frm = str(cm.get(3, "") or "").strip()
                    body = str(cm.get(5, "") or "").strip()
                    if BOT_MASTER and frm == BOT_MASTER and body:
                        # Reuse room command handling with the command-context room.
                        ctx_room = self.room
                        if body.lower().startswith(("inv", "دعوات", "invite")):
                            parts = body.split()
                            target_room = parts[1] if len(parts) > 1 else ctx_room
                            self.request_occupants(target_room)
                        elif body.lower().startswith(("دخول ", "join ", "ادخل ", "enter ")):
                            parts = body.split(None, 1)
                            if len(parts) == 2 and parts[1].strip():
                                target_room = parts[1].strip()
                                self.join_room(target_room)
                                self.known_rooms.add(target_room)
                                self.send_private_text(BOT_MASTER, f"✅ دخلت الغرفة: {target_room} | الغرف الحالية: {len(self.known_rooms)}")
                except Exception as e:
                    self.log("[CHAT_MESSAGE] private command handling failed:", repr(e))
            if result.get("type") or result.get("value"):
                self.log("[RESULT]", result.get("type"), result.get("value"))
        except Exception as e:
            self.last_error = str(e)
            self.log("[WS] decode error:", repr(e))
            if DEBUG and isinstance(message, (bytes, bytearray)):
                self.log("[WS] raw:", bytes(message).hex()[:1000])

    def on_open(self, ws):
        # Room join is deliberately performed once by bootstrap_after_connect(),
        # after the server handshake/bootstrap frame. Joining here as well can
        # cause duplicate join/leave events on some server sessions.
        self.log("[WS] connected:", self.websocket_url())

    def on_error(self, ws, error):
        self.last_error = str(error)
        self.log("[WS] error:", error)

    def on_close(self, ws, code, msg):
        self.log("[WS] closed:", code, msg)

    def bootstrap_after_connect(self):
        """Wait briefly for the server bootstrap, then request the room lists."""
        deadline = time.time() + float(os.getenv("BOOTSTRAP_WAIT", "6"))
        got_server_frame = False

        while time.time() < deadline:
            remaining = max(0.2, deadline - time.time())
            old_timeout = getattr(self.ws, "timeout", 20)
            try:
                self.ws.sock.settimeout(min(remaining, 1.0))
                kind, message = self.ws.recv()
            except socket.timeout:
                continue
            finally:
                try:
                    self.ws.sock.settimeout(old_timeout)
                except Exception:
                    pass

            if kind == "ping":
                continue
            if kind == "pong":
                continue
            if kind == "close":
                raise ConnectionError(f"WebSocket closed during server bootstrap: {message}")
            if kind != "binary":
                continue

            got_server_frame = True
            self.on_message(self.ws, message)

            # First valid server result is the synchronization point used
            # before room-list loading.
            try:
                # Newer TalkinChat builds expose this request name directly.
                self.send_query(encode_query("load_list_new"))
                self.log("[BOOTSTRAP] sent load_list_new")
            except Exception as e:
                self.log("[BOOTSTRAP] load_list_new failed:", repr(e))
            break

        if not got_server_frame:
            # Do not hang forever if a build/server does not send an initial
            # unsolicited frame. Still request the list exactly once.
            try:
                self.send_query(encode_query("load_list_new"))
                self.log("[BOOTSTRAP] no unsolicited frame; sent load_list_new")
            except Exception as e:
                self.log("[BOOTSTRAP] list request failed:", repr(e))

        # Give the server a short window to return list data before joining.
        list_deadline = time.time() + float(os.getenv("LIST_BOOTSTRAP_WAIT", "2"))
        while time.time() < list_deadline:
            remaining = min(0.8, max(0.1, list_deadline - time.time()))
            old_timeout = getattr(self.ws, "timeout", 20)
            try:
                self.ws.sock.settimeout(remaining)
                kind, message = self.ws.recv()
            except socket.timeout:
                continue
            finally:
                try:
                    self.ws.sock.settimeout(old_timeout)
                except Exception:
                    pass
            if kind == "binary":
                self.on_message(self.ws, message)
            elif kind == "ping":
                continue
            elif kind == "close":
                raise ConnectionError(f"WebSocket closed during room-list bootstrap: {message}")

        # Rejoin every room known before a socket interruption. This prevents
        # a reconnect from silently dropping previously joined rooms.
        self.known_rooms.add(self.room)
        rooms_to_join = [r for r in self.known_rooms if r]
        self.log("[ROOM] reconnecting to rooms:", rooms_to_join)
        for joined_room in rooms_to_join:
            try:
                self.join_room(joined_room)
                time.sleep(0.25)
            except Exception as e:
                self.log("[ROOM] rejoin failed:", joined_room, repr(e))

    def run_once(self):
        self.authenticate()
        # Android saves AuthResult.server into SharedPreferences and then
        # Client uses that saved server for the WebSocket. Do the same:
        # authenticated server first, configured default only as fallback.
        ports = []
        # AuthResult.server is the server selected by TalkinChat for this
        # account/session. Prefer it and only use SOCKET_PORT if auth did not
        # provide a server.
        auth_port = getattr(self, "auth_server", "")
        if auth_port:
            ports.append(auth_port)
        elif DEFAULT_PORT:
            ports.append(DEFAULT_PORT)
        if not ports:
            ports = ["5335"]

        # Exact default 5.8.3 Client.smali branch: Client reads `default/m`
        # with default `n`, then calls M9/c.c(), which supplies only `b`.
        # This is also the branch that previously reached HTTP 101 on this server.
        header_lines = self.app_ws_headers()

        last_error = None
        # Client.smali constructs only chatp.net:<server>/server. The CDN entry
        # seen in the connection monitor is not used by this Talkin Client path,
        # so do not treat it as a WebSocket fallback.
        for port in ports:
            self.port = port
            for host in WS_HOSTS:
                self.ws_host = host
                for path in WS_PATHS:
                    self.ws_path = path
                    url = self.websocket_url(path)
                    self.log("[WS] trying host/port/path:", host, port, path, url)
                    try:
                        # Y9/v Client.smali does not copy the HTTP auth Session
                        # cookies into the WebSocket handshake. Keep the WS request
                        # limited to the headers actually built by the APK.
                        self.ws = RawWebSocket(url, list(header_lines), timeout=20, debug=RAW_DIAGNOSTIC)
                        self.ws.connect()
                        self.log("[WS] CONNECTED:", url)
                        self.log("[WS] custom headers:", [x.split(":",1)[0] + ": <redacted>" if x.lower().startswith(("username:", "password:")) else x for x in header_lines])
                        # Short reads allow keepalive while the room is silent.
                        # Idle timeouts are never treated as disconnects.
                        self.ws.sock.settimeout(max(1.0, WS_IDLE_READ_TIMEOUT))
                        last_keepalive = time.monotonic()
                        self.bootstrap_after_connect()

                        while not self.stop_event.is_set():
                            try:
                                kind, message = self.ws.recv()
                            except socket.timeout:
                                # The room may be completely silent. Keep the SAME
                                # WebSocket alive with a control ping; never reconnect
                                # merely because no room message arrived.
                                now = time.monotonic()
                                if now - last_keepalive >= WS_KEEPALIVE_INTERVAL:
                                    self.ws.send_control(0x9, b"janit-keepalive")
                                    last_keepalive = now
                                    self.log("[WS] keepalive ping sent (idle room)")
                                continue
                            if kind == "binary":
                                self.on_message(self.ws, message)
                            elif kind == "ping":
                                continue
                            elif kind == "pong":
                                continue
                            elif kind == "text":
                                self.log("[WS] unexpected text frame:", message[:300])
                            elif kind == "close":
                                raise ConnectionError(f"WebSocket closed by server: {message}")
                        return
                    except Exception as e:
                        last_error = e
                        self.log("[WS] host/path failed:", host, port, path, repr(e))
                        try:
                            if self.ws:
                                self.ws.close()
                        except Exception:
                            pass
                        self.ws = None
        raise last_error

    def start(self):
        print("=== Talkinchat Bot V16 - Master Room Join + Normal Private Invites ===", flush=True)
        if not BOT_ID or not BOT_PWD or not self.room:
            raise SystemExit("Set BOT_USERNAME, BOT_PASSWORD, MASTER_USERNAME and FIRST_ROOM in Railway Variables.")
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                self.last_error = str(e)
                print("[BOT] error:", repr(e), flush=True)
            if not self.stop_event.is_set():
                print("[BOT] reconnecting in 3s...", flush=True)
                time.sleep(3)


if __name__ == "__main__":
    TalkinBot().start()
