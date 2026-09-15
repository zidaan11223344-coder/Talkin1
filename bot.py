import base64
import json
import os
import random
import secrets
import ssl
import socket
import struct
import hashlib
import threading
import time
import uuid
import subprocess
import shutil
import re
import queue
import mimetypes
import unicodedata
import html
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, unquote
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from collections import defaultdict
from pathlib import Path

import requests
try:
    from supabase import create_client
except Exception:
    create_client = None
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# Media / music / gifts ported from the supplied Giant bot + Talkin APK.
# The actual Talkin transport remains the authoritative transport.
# ============================================================
try:
    import yt_dlp
except Exception:
    yt_dlp = None
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, features
    PIL_AVAILABLE = True
except Exception:
    Image = ImageDraw = ImageFont = None
    PIL_AVAILABLE = False
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:
    arabic_reshaper = None
    get_display = None

MUSIC_MAX_SECONDS = int(os.getenv("MUSIC_MAX_SECONDS", "900"))
MUSIC_COOLDOWN = float(os.getenv("MUSIC_COOLDOWN", "15"))
# Optional YouTube Netscape cookies supplied as a Railway secret variable.
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "").strip()
YOUTUBE_COOKIE_FILE = None
if YOUTUBE_COOKIES:
    try:
        cookie_text = YOUTUBE_COOKIES.replace("\\n", "\n").replace("\\t", "\t")
        if not cookie_text.startswith("# Netscape HTTP Cookie File"):
            cookie_text = "# Netscape HTTP Cookie File\n" + cookie_text
        YOUTUBE_COOKIE_FILE = "/tmp/youtube_cookies.txt"
        Path(YOUTUBE_COOKIE_FILE).write_text(cookie_text, encoding="utf-8")
    except Exception:
        YOUTUBE_COOKIE_FILE = None

# Gift images copied verbatim from the supplied Giant Chat bot assets/.
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
# Gift source images: accept PNG/JPG/JPEG from assets/.
# This keeps the bot working even if the original PNG files are replaced by JPG files.
GIFT_IMAGE_FILES = {
    str(i): [
        path
        for variant in (1, 2, 3)
        for ext in ("png", "jpg", "jpeg")
        for path in [ASSETS_DIR / f"gift_{i:02d}_{variant}.{ext}"]
        if path.is_file()
    ]
    for i in range(1, 15)
}
# الألعاب وصورها معطلة بناءً على إعداد البوت المطلوب؛ لا تُرسل صور ألعاب.
GAME_IMAGE_FILES = {
    "bet": "game_bet.jpg",
    "million": "game_million.jpg",
    "duel": "game_duel.jpg",
    "luck": "game_luck.jpg",
    "investment": "game_investment.jpg",
    # New global fixed-prize games.
    "صيد": "game_hunt_fishing.jpg",
    "سرعة": "game_speed.jpg",
    "كنز": "game_treasure.jpg",
    "مصارعة": "game_battle.jpg",
    "بحث": "game_search.jpg",
    "اسرق_نجاح": "game_steal_success.jpg",
    "اسرق_فشل": "game_steal_failure.jpg",
}
GAME_COMMANDS = {}
# Railway exposes this service through RAILWAY_PUBLIC_DOMAIN after a public domain is generated.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
GIFT_PUBLIC_BASE_URL = os.getenv("GIFT_PUBLIC_BASE_URL", "").strip().rstrip("/")
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()

def _public_base_url():
    domain = RAILWAY_PUBLIC_DOMAIN
    if domain:
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
        return domain.rstrip("/")
    return (PUBLIC_BASE_URL or GIFT_PUBLIC_BASE_URL).rstrip("/")

MEDIA_PUBLIC_BASE_URL = _public_base_url()
ASSET_HTTP_PORT = int(os.getenv("PORT", "8080"))
ASSET_HTTP_ENABLED = os.getenv("ASSET_HTTP_ENABLED", "1") == "1"

GIFT_CATALOG = {
    "1": ("🌹", "وردة"), "2": ("❤️", "قلب"), "3": ("😘", "قبلة"),
    "4": ("🧸", "دب"), "5": ("🎂", "كعكة"), "6": ("🎆", "ألعاب نارية"),
    "7": ("⚡", "برق"), "8": ("👑", "تاج"), "9": ("👸", "أميرة"),
    "10": ("🏎️", "سيارة"), "11": ("✈️", "طائرة"), "12": ("🐉", "تنين"),
    "13": ("🚀", "سفينة فضاء"), "14": ("🏰", "قصر"),
}

# ============================================================
# Talkin/ChatP protocol ported from the supplied Android APK.
# The realtime protocol is protobuf over binary WebSocket frames.
# Authentication is protobuf over POST /api?auth_new.
# ============================================================

# Keep the canonical names documented for Railway. The aliases preserve
# compatibility with older deployments that used the original README names.
BOT_ID = (os.getenv("BOT_ID") or os.getenv("BOT_USERNAME") or "").strip()
BOT_PWD = os.getenv("BOT_PWD") or os.getenv("BOT_PASSWORD") or ""
BOT_MASTER = (os.getenv("BOT_MASTER") or os.getenv("MASTER_USERNAME") or "").strip()
PRIMARY_BOT_ID = (os.getenv("PRIMARY_BOT_ID") or "").strip()
INVITE_SENDER_NAME = os.getenv("INVITE_SENDER_NAME", "السفير").strip() or "السفير"
GROUP_TO_JOIN = (os.getenv("GROUP_TO_JOIN") or os.getenv("FIRST_ROOM") or "").strip()
MASTER_SUPPORT_USERNAME = os.getenv(
    "MASTER_SUPPORT_USERNAME",
    "∫♚∫اݪـــۛــ⃮ـاۿــ𓏺𓏺ـيّـــّٰـبــۃ∫♚∫",
).strip()
MASTER_SERVICE_ENABLED = os.getenv("MASTER_SERVICE_ENABLED", "0") == "1"
# Talkin profile-status query can differ between server builds. Keep the
# action configurable while defaulting to the native profile update name.
PROFILE_STATUS_ACTIONS = [x.strip() for x in os.getenv(
    "PROFILE_STATUS_ACTIONS", "update_profile,profile_update,user_update"
).split(",") if x.strip()]
MASTER_DISPLAY_NAME = os.getenv(
    "MASTER_DISPLAY_NAME", "ۦاݪــۛـسـ𓆩♛𓆪ـۧۦـ۫فـيــ۫ـۧر𝁤𝆬𝃛"
).strip()
DEFAULT_BOT_BASE_STATUS = (
    '<h3><p style="background-color:#000000;padding:20px;text-align:center;">'
    '<font color="#b73206" size="7">بوت حمايه والعاب واغاني</font></p>'
    '<b><h2><p style="background-color:#0C090A;">'
    '<font color="#FFE87C">لمعرفه الالعاب والاوامر ارسل مساعده</font></p></h2></b>'
    '<br><br><span style="color:#af0365;font-size:60px;">'
    'لدخول الغرف ارسل دخول اسم الغرفه</span><br>'
    '<span style="color:#66D9FF;font-size:42px;">الماستر: '
    f'{MASTER_DISPLAY_NAME}</span></h3>'
)
BOT_BASE_STATUS = os.getenv("BOT_BASE_STATUS", DEFAULT_BOT_BASE_STATUS).strip()
PROFILE_STATUS_MAX_CHARS = max(300, int(os.getenv("PROFILE_STATUS_MAX_CHARS", "700")))
GIFT_STATUS_SECONDS = 15 * 60

# Master account process control. The primary bot can start/stop master_bot.py
# from the private chat, but only the configured BOT_MASTER is authorized.
MASTER_RUNNER_FILE = BASE_DIR / "master_bot.py"
MASTER_PROCESS_LOCK = threading.Lock()
MASTER_PROCESS = None

def _master_process_running():
    global MASTER_PROCESS
    with MASTER_PROCESS_LOCK:
        if MASTER_PROCESS is not None and MASTER_PROCESS.poll() is None:
            return True
        MASTER_PROCESS = None
        return False

def _start_master_process():
    """Start master_bot.py once, inheriting deployment Secrets from the primary bot."""
    global MASTER_PROCESS
    master_id = os.getenv("MASTER_ID", "").strip()
    master_pwd = os.getenv("MASTER_PWD", "")
    if not master_id or not master_pwd:
        return False, "❌ لم يتم ضبط MASTER_ID و MASTER_PWD في متغيرات الاستضافة."
    if not MASTER_RUNNER_FILE.exists():
        return False, "❌ ملف master_bot.py غير موجود بجانب البوت."
    with MASTER_PROCESS_LOCK:
        if MASTER_PROCESS is not None and MASTER_PROCESS.poll() is None:
            return True, "ℹ️ الماستر يعمل بالفعل."
        env = os.environ.copy()
        env["MASTER_ID"] = master_id
        env["MASTER_PWD"] = master_pwd
        env["MASTER_SERVICE_ENABLED"] = "1"
        env["GROUP_TO_JOIN"] = ""
        env["FIRST_ROOM"] = ""
        env["PRIMARY_BOT_ID"] = BOT_ID
        # Keep the master isolated from primary BOT_ID/BOT_PWD values.
        env.pop("BOT_ID", None)
        env.pop("BOT_PWD", None)
        env.pop("BOT_USERNAME", None)
        env.pop("BOT_PASSWORD", None)
        try:
            MASTER_PROCESS = subprocess.Popen(
                [sys.executable, str(MASTER_RUNNER_FILE)],
                cwd=str(BASE_DIR),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=None,
                stderr=None,
                start_new_session=True,
            )
        except Exception as exc:
            MASTER_PROCESS = None
            return False, f"❌ تعذر تشغيل الماستر: {exc}"
    time.sleep(0.7)
    if MASTER_PROCESS.poll() is not None:
        code = MASTER_PROCESS.returncode
        MASTER_PROCESS = None
        return False, f"❌ توقفت خدمة الماستر مباشرة (رمز الخروج: {code}). راجع سجل الاستضافة."
    return True, "✅ تم تشغيل الماستر."

def _stop_master_process():
    """Stop only the master_bot.py process started by this primary bot."""
    global MASTER_PROCESS
    with MASTER_PROCESS_LOCK:
        proc = MASTER_PROCESS
        MASTER_PROCESS = None
    if proc is None or proc.poll() is not None:
        return True, "ℹ️ الماستر متوقف بالفعل."
    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        return True, "✅ تم إيقاف الماستر."
    except Exception as exc:
        return False, f"❌ تعذر إيقاف الماستر: {exc}"

# Persistent bot data. Runtime code is replaceable; these JSON files are not.
# The data directory can be set once with BOT_DATA_DIR/PERSISTENT_DATA_DIR.
# On Railway, /data/chatbuz_bot is preferred so a mounted volume can keep all
# bot state across deployments. When no volume is mounted, the code falls back
# to a local data/ directory beside bot.py and migrates any old JSON files there.
def _select_persistent_data_dir():
    configured = (os.getenv("BOT_DATA_DIR") or os.getenv("PERSISTENT_DATA_DIR") or "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    # Railway volume mount /data is the recommended permanent location.
    candidates.append(Path("/data/chatbuz_bot"))
    candidates.append(BASE_DIR / "data")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue
    return BASE_DIR / "data"

DATA_DIR = _select_persistent_data_dir()

# Every mutable bot record lives in its own dedicated JSON file.
MASTERS_FILE = DATA_DIR / "masters.json"
VIP_FILE = DATA_DIR / "vip_users.json"
VERIFIED_FILE = DATA_DIR / "verified_users.json"
POINTS_FILE = DATA_DIR / "points.json"
MESSAGES_FILE = DATA_DIR / "messages.json"
PUBLISHED_FILE = DATA_DIR / "published_posts.json"
GAME_STATS_FILE = DATA_DIR / "game_stats.json"
CROP_PLOTS_FILE = DATA_DIR / "crop_plots.json"
TRACKED_ROOMS_FILE = DATA_DIR / "tracked_rooms.json"
BLOCKED_ROOMS_FILE = DATA_DIR / "blocked_rooms.json"
ROOM_USERS_FILE = DATA_DIR / "room_users.json"
INVITE_HISTORY_FILE = DATA_DIR / "invite_history.json"
REPLIES_FILE = DATA_DIR / "replies.json"
MODERATION_FILE = DATA_DIR / "moderation.json"
# Dedicated persistent file for filter words added with +mf@...
MF_FILE = DATA_DIR / "mf.json"
# Dedicated persistent file for accounts allowed to manage VIP verification.
MVIP_MASTERS_FILE = DATA_DIR / "mvip_masters.json"

# Known legacy state files used by older releases. This migration runs once and
# NEVER deletes the old files, so replacing bot.py cannot destroy the old data.
_STATE_FILE_NAMES = (
    "masters.json", "vip_users.json", "verified_users.json", "points.json",
    "messages.json", "published_posts.json", "game_stats.json", "crop_plots.json",
    "tracked_rooms.json", "blocked_rooms.json", "room_users.json", "invite_history.json", "replies.json",
    "moderation.json", "mf.json", "mvip_masters.json", "welcome.json", "custom_welcomes.json", "custom_games.json",
    "custom_commands.json", "repair_state.json",
)

def _json_has_real_data(path):
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return bool(value)
        if isinstance(value, list):
            return bool(value)
        return value not in (None, "", 0, False)
    except Exception:
        return False

def _migrate_legacy_state_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in _STATE_FILE_NAMES:
        target = DATA_DIR / name
        legacy_candidates = [BASE_DIR / name, BASE_DIR / "data" / name]
        # Copy only when the persistent copy is missing/empty. Existing data is
        # never overwritten by a newer bot.py.
        if _json_has_real_data(target):
            continue
        for legacy in legacy_candidates:
            if legacy.resolve() == target.resolve() or not legacy.is_file():
                continue
            try:
                if legacy.stat().st_size <= 0:
                    continue
                shutil.copy2(legacy, target)
                break
            except Exception:
                pass

_migrate_legacy_state_files()
# Restore state from GitHub after the data directory and legacy migration are ready.

# Giant Chat gift costs/labels; images remain the local Giant assets.
GIFT_COSTS = {"1":10,"2":20,"3":30,"4":50,"5":80,"6":150,"7":200,"8":500,"9":800,"10":1000,"11":1500,"12":3000,"13":5000,"14":8000}


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


# Railway has no Android runtime and this bot does not need the phone's
# Android ID or Android system properties for publishing.  Talkin's wire
# protocol still requires device_id/device_model fields, so keep a stable
# synthetic profile in the exact APK fingerprint format without probing Android.
DEVICE_ID = "chatbuz-railway"
_MANUFACTURER = "samsung"
_MODEL = "SM-G998B"
SDK = os.getenv("SDK", "35").strip() or "35"
DEVICE_MODEL = os.getenv("DEVICE_MODEL", "").strip() or (
    "444$" + _MANUFACTURER + "-" + _MODEL + "$" + SDK
)

API_VER = "2"
CLIENT_VER = "1"
AUTH_VER = "444"
AUTH_METHOD = "1"

# Keep these enabled for easy troubleshooting.
DEBUG = os.getenv("DEBUG", "1") == "1"
RAW_DIAGNOSTIC = os.getenv("RAW_DIAGNOSTIC", "0") == "1"
ACK_ROOM_EVENTS = os.getenv("ACK_ROOM_EVENTS", "1") == "1"
AUTO_HELP = os.getenv("AUTO_HELP", "1") == "1"
SAFE_TEXT_PACKET_LIMIT = max(120, int(os.getenv("SAFE_TEXT_PACKET_LIMIT", "260")))
HELP_LINES_PER_MESSAGE = max(1, int(os.getenv("HELP_LINES_PER_MESSAGE", "10")))
HELP_PACKET_MAX_CHARS = max(400, int(os.getenv("HELP_PACKET_MAX_CHARS", "900")))
BANNED_WORDS = {w.strip().lower() for w in os.getenv("BANNED_WORDS", "").split(",") if w.strip()}
AUTO_BAN_WORDS = os.getenv("AUTO_BAN_WORDS", "1") == "1"

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
            self.sock.sendall(hdr + mask + masked)

    def send_control(self, opcode, payload=b''):
        payload = bytes(payload); mask = os.urandom(4)
        if len(payload) > 125: raise ValueError('control frame too large')
        hdr = bytes([0x80 | opcode, 0x80 | len(payload)])
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
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
            # A peer-initiated close must be acknowledged before reconnecting.
            try:
                self.send_control(0x8, data[:125])
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
        """Return all members of a room using paged DB reads.

        Paging prevents large rooms from being truncated by the provider's
        default row limit. Profile lookups are also batched in groups of 100.
        """
        if not self.client:
            return []
        rid = self.room_id(room_name)
        if not rid:
            return []
        try:
            members = []
            page_size = 1000
            offset = 0
            while True:
                r = (self.client.table("room_members")
                     .select("user_id, rank, joined_at, is_present")
                     .eq("room_id", rid)
                     .range(offset, offset + page_size - 1)
                     .execute())
                rows = getattr(r, "data", None) or []
                members.extend(rows)
                if len(rows) < page_size:
                    break
                offset += page_size
            self.last_member_count = len(members)
            ids = []
            for row in members:
                uid = row.get("user_id")
                if uid and str(uid) not in ids:
                    ids.append(str(uid))
            if not ids:
                return []
            out = []
            for i in range(0, len(ids), 100):
                batch = ids[i:i + 100]
                pr = self.client.table("profiles").select("id, username").in_("id", batch).execute()
                for row in (getattr(pr, "data", None) or []):
                    u = str(row.get("username") or "").strip()
                    if u:
                        out.append({"username": u, "user_id": str(row.get("id") or "")})
            seen = set()
            final = []
            for u in out:
                k = u["username"].casefold()
                if k not in seen:
                    seen.add(k)
                    final.append(u)
            self.last_profile_count = len(final)
            self.log(f"[DB] room_members={len(members)} profiles={len(final)} room_id={rid}")
            return final
        except Exception as e:
            self.last_error = str(e)
            self.log("[DB] room_members query failed:", repr(e))
            return []

# ----------------------- Giant-style local data -----------------------
def _load_local_json(path, default):
    try:
        if Path(path).is_file():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _save_local_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    _github_sync_after_local_save(path, data)

# GitHub-backed persistent state. Set GITHUB_TOKEN and GITHUB_REPO in the
# hosting environment to make every JSON state file live in the GitHub repo.
# Never hard-code the token in bot.py. For public repositories, remember that
# committed member/verification/points data becomes publicly readable.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
GITHUB_DATA_DIR = os.getenv("GITHUB_DATA_DIR", "bot_data").strip().strip("/")
GITHUB_SYNC_ENABLED = bool(GITHUB_TOKEN and GITHUB_REPO and os.getenv("GITHUB_SYNC", "1").strip().lower() not in {"0", "false", "no", "off"})
_GITHUB_SYNC_LOCK = threading.RLock()
_GITHUB_SYNC_LAST = {}
_GITHUB_RESTORING = False
_GITHUB_PENDING = {}
_GITHUB_PENDING_CONDITION = threading.Condition()
_GITHUB_WORKER_STARTED = False
_GITHUB_BACKUP_REQUESTS = []

def _github_url(path):
    from urllib.parse import quote
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{quote(path.lstrip('/'), safe='/')}"

def _github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TalkinChat-Bot-Persistent-State",
    }

def _github_state_path(local_path):
    name = Path(local_path).name
    return f"{GITHUB_DATA_DIR}/{name}" if GITHUB_DATA_DIR else name

def _github_get_file(local_path):
    if not GITHUB_SYNC_ENABLED:
        return None
    try:
        r = requests.get(_github_url(_github_state_path(local_path)), headers=_github_headers(), params={"ref": GITHUB_BRANCH}, timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        payload = r.json()
        content = base64.b64decode(payload.get("content", "").replace("\n", "")).decode("utf-8")
        return json.loads(content)
    except Exception as exc:
        print(f"[GITHUB] read failed for {Path(local_path).name}: {exc}", flush=True)
        return None

def _github_put_file(local_path, data, sha=None):
    """Create or update a JSON file in GitHub reliably.

    GitHub requires the current blob SHA when updating an existing file.
    Therefore we fetch the current SHA before every update when the caller
    did not provide one, and retry once after a conflict.
    """
    if not GITHUB_SYNC_ENABLED:
        return False
    name = Path(local_path).name
    url = _github_url(_github_state_path(local_path))
    try:
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        payload = {
            "message": f"chore(bot): update {name}",
            "content": base64.b64encode(raw).decode("ascii"),
            "branch": GITHUB_BRANCH,
        }

        # Existing GitHub files must include their current SHA.
        if not sha:
            current = requests.get(
                url, headers=_github_headers(),
                params={"ref": GITHUB_BRANCH}, timeout=15
            )
            if current.status_code == 200:
                sha = current.json().get("sha")
            elif current.status_code != 404:
                current.raise_for_status()
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=_github_headers(), json=payload, timeout=20)

        # If another process changed the file between GET and PUT, refresh
        # the SHA and retry once.
        if r.status_code in (409, 422):
            rr = requests.get(
                url, headers=_github_headers(),
                params={"ref": GITHUB_BRANCH}, timeout=15
            )
            if rr.status_code == 200:
                new_sha = rr.json().get("sha")
                if new_sha:
                    payload["sha"] = new_sha
                    r = requests.put(
                        url, headers=_github_headers(), json=payload, timeout=20
                    )

        r.raise_for_status()
        print(f"[GITHUB] saved {name}", flush=True)
        return True
    except Exception as exc:
        print(f"[GITHUB] write failed for {name}: {exc}", flush=True)
        return False

def _github_restore_or_seed_state():
    global _GITHUB_RESTORING
    if not GITHUB_SYNC_ENABLED:
        return
    print(f"[GITHUB] persistent state enabled: {GITHUB_REPO}@{GITHUB_BRANCH}/{GITHUB_DATA_DIR}", flush=True)
    _GITHUB_RESTORING = True
    try:
        for name in _STATE_FILE_NAMES:
            local = DATA_DIR / name
            try:
                remote = _github_get_file(local)
                if remote is not None:
                    # GitHub is the durable source. Always restore a non-empty
                    # remote record when the local copy is empty or differs;
                    # this also repairs a stale empty file left on Railway.
                    local_data = _load_local_json(local, None)
                    local_has_data = bool(local_data) if isinstance(local_data, (dict, list)) else local_data not in (None, "", 0, False)
                    remote_has_data = bool(remote) if isinstance(remote, (dict, list)) else remote not in (None, "", 0, False)
                    if (remote_has_data and not local_has_data) or (
                        remote_has_data and local_data != remote
                    ):
                        _save_local_json(local, remote)
                        print(f"[GITHUB] restored {name}", flush=True)
                elif _json_has_real_data(local):
                    _github_put_file(local, _load_local_json(local, None))
                    print(f"[GITHUB] seeded {name}", flush=True)
            except Exception as exc:
                print(f"[GITHUB] startup sync failed for {name}: {exc}", flush=True)
    finally:
        _GITHUB_RESTORING = False

# Restore persistent state only after the GitHub restore function has been defined.
_github_restore_or_seed_state()


def _github_sync_after_local_save(path, data):
    if not GITHUB_SYNC_ENABLED or _GITHUB_RESTORING:
        return
    # Never block the WebSocket/event handler on a GitHub HTTP request. Keep
    # only the latest value for each file and let one worker serialize commits.
    # This is especially important for tracked_rooms/room_users, which may be
    # saved several times while a room is joining.
    try:
        snapshot = json.loads(json.dumps(data, ensure_ascii=False))
    except Exception:
        snapshot = data
    with _GITHUB_PENDING_CONDITION:
        _GITHUB_PENDING[str(path)] = snapshot
        _GITHUB_PENDING_CONDITION.notify()


def _queue_github_full_backup():
    """Queue every existing JSON state file for a non-blocking full backup."""
    if not GITHUB_SYNC_ENABLED:
        return 0
    queued = 0
    for name in _STATE_FILE_NAMES:
        path = DATA_DIR / name
        data = _load_local_json(path, None)
        if path.is_file() and data is not None:
            _github_sync_after_local_save(path, data)
            queued += 1
    return queued


def _request_github_full_backup(bot, sender):
    """Queue a full backup and remember who should receive its result."""
    queued = _queue_github_full_backup()
    if queued:
        with _GITHUB_PENDING_CONDITION:
            _GITHUB_BACKUP_REQUESTS.append((bot, str(sender or "").strip()))
            _GITHUB_PENDING_CONDITION.notify()
    return queued


def _github_sync_worker():
    while True:
        with _GITHUB_PENDING_CONDITION:
            while not _GITHUB_PENDING:
                _GITHUB_PENDING_CONDITION.wait()
            # Coalesce bursts of local writes before making a network request.
            _GITHUB_PENDING_CONDITION.wait(timeout=0.75)
            pending = dict(_GITHUB_PENDING)
            _GITHUB_PENDING.clear()
        backup_ok = True
        for path, data in pending.items():
            try:
                with _GITHUB_SYNC_LOCK:
                    if not _github_put_file(path, data):
                        backup_ok = False
            except Exception as exc:
                backup_ok = False
                print(f"[GITHUB] background sync failed for {Path(path).name}: {exc}", flush=True)
        with _GITHUB_PENDING_CONDITION:
            requests_to_notify = list(_GITHUB_BACKUP_REQUESTS)
            _GITHUB_BACKUP_REQUESTS.clear()
        for bot, sender in requests_to_notify:
            try:
                notice = (
                    "✅ تم النسخ الاحتياطي بنجاح إلى GitHub (Talkin4)."
                    if backup_ok else
                    "❌ اكتمل النسخ الاحتياطي جزئياً؛ تعذر رفع ملف أو أكثر. راجع سجل Railway."
                )
                bot.send_private_text(sender, notice)
            except Exception as exc:
                print(f"[GITHUB] backup completion notice failed: {exc}", flush=True)


if GITHUB_SYNC_ENABLED and not _GITHUB_WORKER_STARTED:
    threading.Thread(target=_github_sync_worker, name="github-sync", daemon=True).start()
    _GITHUB_WORKER_STARTED = True


def _norm_user(name):
    return str(name or "").strip().lstrip("@").casefold()

def _norm_room(name):
    return str(name or "").strip()

def _persistent_rooms():
    data = _load_local_json(TRACKED_ROOMS_FILE, [])
    if isinstance(data, dict):
        data = data.get("rooms", [])
    return sorted({_norm_room(x) for x in (data if isinstance(data, list) else []) if _norm_room(x)})

def _save_persistent_rooms(rooms):
    _save_local_json(TRACKED_ROOMS_FILE, {"version": 1, "rooms": sorted({_norm_room(x) for x in rooms if _norm_room(x)})})

def _persistent_rosters():
    data = _load_local_json(ROOM_USERS_FILE, {})
    return data if isinstance(data, dict) else {}

def _save_persistent_rosters(rosters):
    _save_local_json(ROOM_USERS_FILE, {"version": 1, "rooms": rosters})

def _persistent_roster_users(room):
    data = _persistent_rosters()
    if isinstance(data.get("rooms"), dict):
        data = data["rooms"]
    room_data = data.get(_norm_room(room), {}) if isinstance(data, dict) else {}
    if not isinstance(room_data, dict):
        return []
    result = []
    for key, value in room_data.items():
        if isinstance(value, dict):
            username = str(value.get("username") or key).strip()
        else:
            username = str(value or key).strip()
        if username and _norm_user(username) != _norm_user(BOT_ID):
            result.append(username)
    return result

def _persistent_all_roster_users():
    """Return the unique usernames stored in room_users.json across all rooms."""
    data = _persistent_rosters()
    rooms = data.get("rooms", data) if isinstance(data, dict) else {}
    if not isinstance(rooms, dict):
        return []
    result = {}
    for room, roster in rooms.items():
        if not isinstance(roster, dict):
            continue
        for key, value in roster.items():
            if isinstance(value, dict):
                username = str(value.get("username") or key).strip()
            else:
                username = str(value or key).strip()
            if username and _norm_user(username) != _norm_user(BOT_ID):
                result.setdefault(_norm_user(username), username)
    return sorted(result.values(), key=lambda x: _norm_user(x))

def _format_saved_accounts(title, data, empty_text):
    """Format a persistent verification/VIP dictionary for the master."""
    if not isinstance(data, dict):
        data = {}
    users = []
    for key, value in data.items():
        if isinstance(value, dict):
            username = str(value.get("username") or key).strip()
        else:
            username = str(value or key).strip()
        if username and _norm_user(username) != _norm_user(BOT_ID):
            users.append(username)
    unique = {}
    for username in users:
        unique.setdefault(_norm_user(username), username)
    users = sorted(unique.values(), key=lambda x: _norm_user(x))
    if not users:
        return empty_text
    lines = [f"{title} ({len(users)}):"]
    lines.extend(f"{i}. @{username}" for i, username in enumerate(users, 1))
    return "\n".join(lines)


def _remember_roster(room, users):
    room = _norm_room(room)
    if not room:
        return
    all_data = _persistent_rosters()
    rosters = all_data.get("rooms", all_data) if isinstance(all_data, dict) else {}
    if not isinstance(rosters, dict):
        rosters = {}
    current = rosters.get(room, {})
    if not isinstance(current, dict):
        current = {}
    now = int(time.time())
    for user in users or []:
        if not isinstance(user, dict):
            continue
        username = str(user.get("username") or "").strip()
        if not username or _norm_user(username) == _norm_user(BOT_ID):
            continue
        current[_norm_user(username)] = {
            "username": username,
            "role": str(user.get("role") or "none").strip().lower() or "none",
            "user_id": str(user.get("user_id") or ""),
            "last_seen": now,
        }
    rosters[room] = current
    _save_persistent_rosters(rosters)


def _master_list():
    data=_load_local_json(MASTERS_FILE, [])
    return data if isinstance(data,list) else []

def _is_master_name(name):
    n=_norm_user(name)
    return bool(n and (n == _norm_user(BOT_MASTER) or n in {_norm_user(x) for x in _master_list()}))
def _mvip_master_list():
    data = _load_local_json(MVIP_MASTERS_FILE, [])
    return data if isinstance(data, list) else []

def _is_mvip_master(name):
    key = _norm_user(name)
    return bool(key and (key in {_norm_user(x) for x in _mvip_master_list()} or _is_primary_master(name)))

def _is_verification_manager(name):
    return _is_master_name(name) or _is_mvip_master(name)

def _is_verification_manager_command(text):
    value = str(text or "").strip()
    return bool(
        re.match(r"^(?:vi|uns|vip|unvip|un vip)@.+$", value, re.I)
        or value.casefold() in {"l@mvip"}
    )

def _is_primary_master(name):
    """Only the account configured in BOT_MASTER has unlimited points."""
    n=_norm_user(name)
    return bool(n and n == _norm_user(BOT_MASTER))
def _verification_notice():
    master = BOT_MASTER or "الماستر"
    return f"🔒 حسابك ليس موثقاً.\n📩 يرجى مراسلة الماستر لتوثيق حسابك @{master}"

def _looks_like_bot_command(text):
    """Recognize commands before the verification gate without blocking normal chat."""
    low = str(text or "").strip().casefold()
    if not low:
        return False
    prefixes = (
        "sa@", ".sa ", "vi@", "vip@", "unvip@", "uns@", "ازالة توثيق@", "إزالة توثيق@",
        "b@", "bl@", "k@", "u@", "ub@", "a@", "o@", "ban ", "kick ", "unban ", "admin ", "owner ",
        "mas@", "umas@", "mvip@", "umvip@", "l@mvip", "l@mas", "sb@", "i@", "inv", "دعوات", "invite", "mvip@", "umvip@", "l@mvip", "l@mas", "خروج",
        "say ", "قل ", "تحويل للكل@", "help", "اوامر", "المسترات", "نقاطي", "points", "توب", "top", "هدايا", "gifts", "gv", "sher@",
        "العاب", "ألعاب", "حظ", "نرد", "تخمين", "سؤال", "حجر", "ورق", "مقص", "مليون", "مراهنة@", "رهان@", "مضاربة@", "استثمار@", "حظي@", "زرع", "فيس", "كنز", "اسرق", "رشوة", "انشر", "تشغيل الحماية", "تشغيل الحمايه", "إيقاف الحماية", "ايقاف الحماية", "mr@",
        "+sr@", "sr@", "swc", "mf@", "+mf@", "-mf@", "l@mf", "clear@mf", "شبيه@", "شبيه ", "شبيهك@", "شبيهك ",
    )
    prefixes = prefixes + ("bl@",)
    return low.startswith(prefixes) or low in ("help", "مساعدة", "games", "game") or low in {x.casefold() for x in GAME_COMMANDS}

def _looks_like_admin_command(text):
    low = str(text or "").strip().casefold()
    prefixes = (
        "vi@", "vip@", "unvip@", "uns@", "ازالة توثيق@", "إزالة توثيق@", "mas@", "umas@", "sb@",
        "b@", "bl@", "k@", "u@", "ub@", "a@", "o@", "ban ", "kick ", "unban ", "admin ", "owner ",
        "i@", "inv", "دعوات", "invite", "mvip@", "umvip@", "l@mvip", "l@mas", "خروج", "say ", "قل ", "انشر", "+sr@", "sr@",
        "swc", "mf@", "+mf@", "-mf@", "l@mf", "clear@mf", "توثيق الكل", "وثق الكل", "verify",
    )
    return low.startswith(prefixes)

def _verified_data():
    data=_load_local_json(VERIFIED_FILE,{})
    return data if isinstance(data,dict) else {}

def _vip_data():
    data=_load_local_json(VIP_FILE,{})
    return data if isinstance(data,dict) else {}

def _is_verified_user(name):
    key = _norm_user(name)
    return bool(key and (key in _verified_data() or key in _vip_data() or _is_master_name(name)))

def _is_vip_user(name):
    key = _norm_user(name)
    return bool(key and (key in _vip_data() or _is_master_name(name)))


def _game_stats_data():
    data = _load_local_json(GAME_STATS_FILE, {})
    return data if isinstance(data, dict) else {}


def _record_game(username, game_key, points_delta=0, stake=0):
    key = _norm_user(username)
    if not key or _is_primary_master(username):
        return
    data = _game_stats_data()
    item = data.get(key, {"username": str(username).strip().lstrip("@"), "games": {}})
    item["username"] = str(username).strip().lstrip("@")
    games = item.get("games") if isinstance(item.get("games"), dict) else {}
    g = games.get(game_key, {"plays": 0, "points": 0, "staked": 0})
    g["plays"] = int(g.get("plays", 0) or 0) + 1
    g["points"] = int(g.get("points", 0) or 0) + int(points_delta or 0)
    g["staked"] = int(g.get("staked", 0) or 0) + int(stake or 0)
    games[game_key] = g
    item["games"] = games
    data[key] = item
    _save_local_json(GAME_STATS_FILE, data)


def _game_stats(username, game_key):
    item = _game_stats_data().get(_norm_user(username), {})
    games = item.get("games", {}) if isinstance(item, dict) else {}
    g = games.get(game_key, {}) if isinstance(games, dict) else {}
    return {"plays": int(g.get("plays", 0) or 0), "points": int(g.get("points", 0) or 0), "staked": int(g.get("staked", 0) or 0)}


def _game_level(username):
    item = _game_stats_data().get(_norm_user(username), {})
    games = item.get("games", {}) if isinstance(item, dict) else {}
    plays = sum(int((v or {}).get("plays", 0) or 0) for v in games.values()) if isinstance(games, dict) else 0
    levels = ((0, "مبتدئ"), (10, "لاعب نشيط"), (50, "لاعب محترف"), (150, "أسطورة الألعاب"), (500, "ملك الألعاب"), (1000, "سيد الألعاب"))
    level = levels[0][1]
    for threshold, label in levels:
        if plays >= threshold:
            level = label
    return plays, level


def _game_top(game_key, limit=10):
    rows = []
    for key, item in _game_stats_data().items():
        if not isinstance(item, dict): continue
        games = item.get("games", {})
        g = games.get(game_key, {}) if isinstance(games, dict) else {}
        plays = int(g.get("plays", 0) or 0)
        points = int(g.get("points", 0) or 0)
        staked = int(g.get("staked", 0) or 0)
        if plays: rows.append((points, staked, plays, item.get("username", key)))
    rows.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return rows[:limit]

def _points_data():
    data=_load_local_json(POINTS_FILE,{})
    return data if isinstance(data,dict) else {}

def _add_points(username, amount):
    amount=int(amount)
    data=_points_data(); key=_norm_user(username)
    item=data.get(key,{"username":str(username).strip().lstrip("@"),"points":0})
    item["username"]=str(username).strip().lstrip("@")
    item["points"]=int(item.get("points",0) or 0)+amount
    data[key]=item; _save_local_json(POINTS_FILE,data)
    return item["points"]

def _get_points(username):
    if _is_primary_master(username): return None
    item=_points_data().get(_norm_user(username),{})
    return int(item.get("points",0) or 0)

def _fmt_points(value):
    """Compact point balances for chat: 1,000 -> 1k and 1,000,000 -> 1m."""
    if value is None:
        return "♾️"
    try:
        number = int(value)
    except Exception:
        return str(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000:
        amount = number / 1_000_000
        text = f"{amount:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{text}m"
    if number >= 1_000:
        amount = number / 1_000
        text = f"{amount:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{text}k"
    return f"{sign}{number}"

DEFAULT_REPLY_MESSAGES = {
    "master_silent": "",
    "master_denied": "",
    "game_invalid_amount": "❌ المبلغ يجب أن يكون أكبر من صفر.",
    "game_insufficient": "❌ رصيدك غير كافٍ. رصيدك الحالي: {balance} نقطة.",
    "wager_open": "🎯 {game_label} جديد\n━━━━━━━━━━━━\n👤 {verb}: @{username}\n💰 المبلغ: {amount} نقطة\n\n🤝 للمشاركة ارسل: {command}@{amount}\n━━━━━━━━━━━━",
    "wager_result": "🏆 انتهى {game}\n━━━━━━━━━━━━\n🥊 @{p1} × @{p2}\n\n👑 الفائز: @{winner}\n💰 مبلغ الجولة: {amount} نقطة\n🎁 مكسب الفائز: +{amount} نقطة\n📉 الخاسر: @{loser} (-{amount} نقطة)\n━━━━━━━━━━━━",
    "luck_result": "🍀✨ حظ\n━━━━━━━━━━━━\n👤 اللاعب: @{username}\n🎯 النتيجة: {result}\n💰 الرهان: {amount} نقطة\n💵 التغير: {delta} نقطة\n💳 الرصيد: {balance} نقطة",
}


def _points_summary_text(username):
    pts = _get_points(username)
    if pts is None:
        return "♾️ نقاطك: لا محدود\n👑 الماستر لا يُخصم منه رصيد."
    plays, level = _game_level(username)
    labels=[("رهان","bet"),("مضاربة","duel"),("مليون","million"),("حظي","luck"),("استثمار","investment"),("حظ","luck_free"),("حجر/ورق/مقص","rps"),("زرع","farm"),("فيس","fruit"),("ألعاب أخرى","misc")]
    details=[]
    for label,key in labels:
        g=_game_stats(username,key)
        details.append(f"🎮 {label}: لعب {g['plays']} | نقاط {g['points']:+d} | رهان {g['staked']}")
    return (f"💰 نقاطي\n━━━━━━━━━━━━\n👤 @{str(username).strip().lstrip('@')}\n"
            f"💰 الرصيد: {_fmt_points(pts)}\n⭐ المستوى: {level}\n🎮 إجمالي مرات اللعب: {plays}\n"
            + "\n".join(details))

def _ensure_replies_file():
    data = _load_local_json(REPLIES_FILE, {})
    if not isinstance(data, dict):
        data = {}
    messages = data.get("messages") if isinstance(data.get("messages"), dict) else {}
    changed = False
    for key, value in DEFAULT_REPLY_MESSAGES.items():
        if key not in messages:
            messages[key] = value
            changed = True
    data["messages"] = messages
    if not isinstance(data.get("auto_replies"), dict):
        # Migrate the older auto_replies.json format once.
        legacy = _load_local_json(BASE_DIR / "auto_replies.json", {})
        legacy_replies = legacy.get("replies", {}) if isinstance(legacy, dict) else {}
        data["auto_replies"] = legacy_replies if isinstance(legacy_replies, dict) else {}
        data["auto_replies_enabled"] = bool(legacy.get("enabled", True)) if isinstance(legacy, dict) else True
        changed = True
    if "auto_replies_enabled" not in data:
        data["auto_replies_enabled"] = True
        changed = True
    if changed or not REPLIES_FILE.is_file():
        _save_local_json(REPLIES_FILE, data)
    return data

def _reply_template(key, default="", **kwargs):
    data = _ensure_replies_file()
    messages = data.get("messages", {}) if isinstance(data, dict) else {}
    text = messages.get(key, default) if isinstance(messages, dict) else default
    try:
        return str(text).format(**kwargs)
    except Exception:
        return str(text)

def _load_moderation_config():
    # Prefer the dedicated mf.json file. If it does not exist yet, migrate the
    # existing words from moderation.json into it without deleting old data.
    mf_data = _load_local_json(MF_FILE, {})
    moderation_data = _load_local_json(MODERATION_FILE, {})
    if not isinstance(mf_data, dict):
        mf_data = {}
    if not isinstance(moderation_data, dict):
        moderation_data = {}

    words = mf_data.get("words")
    if not isinstance(words, list):
        words = moderation_data.get("words")
        if isinstance(words, dict):
            words = list(words.keys())
        if not isinstance(words, list):
            words = sorted(BANNED_WORDS)

    words = [str(w).strip() for w in words if str(w).strip()]
    raw_enabled = mf_data.get("enabled", moderation_data.get("enabled", AUTO_BAN_WORDS))
    enabled = bool(raw_enabled) if isinstance(raw_enabled, (bool, int)) else AUTO_BAN_WORDS

    # Ensure the dedicated file exists immediately so filter data is visibly
    # stored separately from the main moderation settings.
    clean = _save_mf_config(enabled, words)
    return enabled, clean

def _save_mf_config(enabled, words):
    clean = []
    seen = set()
    for word in words or []:
        word = str(word).strip()
        if not word:
            continue
        key = _norm_filter_text(word)
        if key and key not in seen:
            seen.add(key)
            clean.append(word)
    _save_local_json(MF_FILE, {"enabled": bool(enabled), "words": clean})
    return clean

def _save_moderation_config(enabled, words):
    clean = []
    seen = set()
    for word in words or []:
        word = str(word).strip()
        if not word:
            continue
        key = _norm_filter_text(word)
        if key and key not in seen:
            seen.add(key)
            clean.append(word)
    _save_local_json(MODERATION_FILE, {"enabled": bool(enabled), "words": clean})
    _save_local_json(MF_FILE, {"enabled": bool(enabled), "words": clean})
    return clean

def _room_moderation_data():
    data = _load_local_json(MODERATION_FILE, {})
    return data if isinstance(data, dict) else {}

def _room_moderation_config(room):
    data = _room_moderation_data()
    rooms = data.get("rooms", {}) if isinstance(data.get("rooms"), dict) else {}
    cfg = rooms.get(_norm_room(room), {})
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "repeat_limit": max(2, int(cfg.get("repeat_limit", 3) or 3)),
        "words": [str(w).strip() for w in cfg.get("words", []) if str(w).strip()],
    }

def _save_room_moderation(room, **changes):
    data = _room_moderation_data()
    rooms = data.get("rooms", {}) if isinstance(data.get("rooms"), dict) else {}
    key = _norm_room(room)
    cfg = _room_moderation_config(room)
    cfg.update(changes)
    cfg["repeat_limit"] = max(2, int(cfg.get("repeat_limit", 3) or 3))
    rooms[key] = cfg
    data["rooms"] = rooms
    # Keep the legacy global filter fields intact for backward compatibility.
    _save_local_json(MODERATION_FILE, data)
    return cfg

def _room_manager(bot, room, sender):
    if _is_master_name(sender):
        return True
    users = getattr(bot, "room_users", {}).get(room, {})
    role = str(users.get(sender, "") or "").casefold()
    if not role and isinstance(users, dict):
        role = next((str(v or "").casefold() for k, v in users.items() if _norm_user(k) == _norm_user(sender)), "")
    # Room protection is intentionally limited to the room creator/owner and
    # configured masters. Ordinary room admins/moderators cannot toggle it.
    return role in {"owner", "creator", "room_owner", "room_creator"}

def _norm_filter_text(text):
    value = str(text or "").casefold()
    value = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", value)
    value = value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    value = value.replace("ى", "ي")
    value = re.sub(r"\s+", "", value)
    return value

def _message_template(section,key,default,**kwargs):
    data=_load_local_json(MESSAGES_FILE,{})
    value=((data.get(section) or {}).get(key)) if isinstance(data,dict) else None
    text=value if isinstance(value,str) else default
    try: return text.format(**kwargs)
    except Exception: return text

def _command_menu():
    return _command_menu_for(False)

def _command_menu_for(is_master=False, is_private=False):
    # help1 contains management commands and is shown only to masters in private chat.
    if is_master and is_private:
        return (
            "📚 أوامر البوت\n"
            "━━━━━━━━━━━━\n"
            "help1 — الإدارة\n"
            "help2 — الموسيقى والتفاعلات\n"
            "help3 — الألعاب\n"
            "help4 — الهدايا والنشر\n"
            "help5 — النقاط\n"
            "help6 — الغرف\n"
            "━━━━━━━━━━━━\n"
            "اكتب\nhelp1 إلى help6 لعرض الأوامر"
        )
    return (
        "📚 أوامر البوت\n"
        "━━━━━━━━━━━━\n"
        "help2 — الموسيقى والتفاعلات\n"
        "help3 — الألعاب\n"
        "help4 — الهدايا والنشر\n"
        "help5 — النقاط\n"
        "help6 — الغرف\n"
        "━━━━━━━━━━━━\n"
        "اكتب help2 إلى help6 لعرض الأوامر"
    )


def _default_help_sections():
    """Complete help catalog. Each help page may contain multiple sections.

    ``Ns`` advances to the next section within the same help page.
    """
    return {
        1: [
            '📋 أوامر الإدارة — 1\n━━━━━━━━━━━━\nk@اسم — طرد عضو\nkick اسم — طرد عضو\nb@اسم — حظر عضو\nban اسم — حظر عضو\nbl@اسم — حظر عضو بالقائمة\nub@اسم — فك الحظر\nu@اسم — فك الحظر\nunban اسم — فك الحظر\na@اسم — تعيين إداري\nadmin اسم — تعيين إداري\no@اسم — تعيين أونر/مالك\nowner اسم — تعيين أونر/مالك',
            '📋 أوامر الإدارة — 2\n━━━━━━━━━━━━\nتشغيل الحماية — تشغيل حماية الغرفة\nإيقاف الحماية — إيقاف حماية الغرفة\nmr@عدد — تحديد حد التكرار\nنسخ احتياطي — إنشاء نسخة احتياطية\nإعادة تشغيل البوت — إعادة تشغيل البوت\nتشغيل الماستر — تشغيل حساب الماستر\nإيقاف الماستر — إيقاف حساب الماستر\nحالة الماستر — حالة حساب الماستر\n\n📌 هذه الأوامر مخصصة للماستر/الإدارة حسب صلاحية الأمر.',
        ],
        2: [
            '🎵 الموسيقى — 1\n━━━━━━━━━━━━\n.sa اسم الأغنية — تشغيل أغنية\nsher@اسم — مشاركة آخر أغنية مع مستخدم\n\nمثال:\n.sa يا ليل\nsher@ahmd555\n\n🔒 تشغيل الأغاني للحسابات الموثقة.',
            '❤️ التفاعلات والشبيه — 2\n━━━━━━━━━━━━\n👍 lk@كود — إعجاب\n❤️ lv@كود — حب\n👎 dl@كود — عدم إعجاب\n💬 cm@كود نص — تعليق\n🚨 report@كود نص — إبلاغ\n\nشبيه@اسم — البحث عن الشبيه\nشبيهك@اسم — البحث عن شبيهك\n\n📌 التفاعل يكون على كود المنشور/المحتوى المرسل من البوت.',
        ],
        3: [
            '🎮 الألعاب — 1: التحديات\n━━━━━━━━━━━━\nالعاب / ألعاب / لعب / games / game — عرض قائمة الألعاب\nرهان@المبلغ — رهان لاعب ضد لاعب\nمراهنة@المبلغ — مراهنة لاعب ضد لاعب\nمضاربة@المبلغ — مضاربة لاعب ضد لاعب\nاستثمار@المبلغ — استثمار لاعب ضد لاعب\nحظي@المبلغ — تحدي حظ لاعب ضد لاعب\nاستثمار — استثمار مجاني مع البوت\nحظ@المبلغ — حظ بمبلغ\nحظ — حظ عشوائي\nحجر / ورق / مقص — لعبة ضد البوت',
            '🎮 الألعاب — 2: الألعاب الفردية\n━━━━━━━━━━━━\nمليون — لعبة المليون\nزرع@رمز_المحصول — زراعة محصول\nفيس@الرمز — مطابقة/تحدي الفيس\nاسرق — سرقة عشوائية من عضو\nاسرق@اسم — سرقة من عضو محدد\nاسرق اسم — سرقة من عضو محدد\n\n🌱 الزراعة: حتى 5 أنواع مختلفة في نفس الوقت.\n📌 كل لعبة لها نظام تبريد خاص بها عند تطبيقه.',
            '🎮 الألعاب — 3: الألعاب العالمية\n━━━━━━━━━━━━\nصيد — تحدي عالمي، الفائز +500\nسرعة — تحدي عالمي، الفائز +500\nكنز — تحدي عالمي، الفائز +500\nمصارعة — تحدي عالمي، الفائز +500\nبحث — تحدي عالمي، الفائز +500\n\n📌 أول لاعب يفتح الجولة، والثاني ينضم من أي غرفة موجود فيها البوت.\n📌 نتيجة الجولة والصورة تظهر للمشاركين فقط.',
        ],
        4: [
            '🎁 الهدايا — 1\n━━━━━━━━━━━━\nsa@رقم@اسم — إرسال هدية\nهدايا — عرض/فتح نظام الهدايا\ngifts — الهدايا\ngv — الهدايا\n\n🔒 المرسل والمستلم يجب أن يكونا موثقين/مسموحاً لهما بالنظام.\n💰 يتم خصم قيمة الهدية من رصيد النقاط.',
            '📢 النشر — 2\n━━━━━━━━━━━━\nانشر — تجهيز ونشر صورة\nانشر@وصف — نشر صورة مع وصف\n\n📌 أرسل الصورة بعد أمر انشر عندما يطلب البوت ذلك.\n📌 النشر متاح للحسابات المسموح لها حسب إعدادات البوت.',
        ],
        5: [
            '💰 النقاط — 1\n━━━━━━━━━━━━\nنقاطي — عرض الرصيد والمستوى وإحصاءات اللعب\npoints — عرض النقاط\nتوب — المتصدرين العام\ntop — المتصدرين العام\n\nتوب رهان — متصدروا الرهان\nتوب مضاربة — متصدروا المضاربة\nتوب حظي — متصدروا حظي\nتوب استثمار — متصدروا الاستثمار',
            '💸 النقاط — 2: التحويل\n━━━━━━━━━━━━\nsb@اسم@عدد — تحويل نقاط لمستخدم\n\nمثال:\nsb@ahmd555@1000\n\n📌 التحويل متاح للمستخدم الموثق، ويُخصم من رصيد المرسل ويُضاف للمستلم.\n\nللاطلاع على الرصيد استخدم: نقاطي',
        ],
        6: [
            '🚪 الغرف — 1\n━━━━━━━━━━━━\nدخول@اسم_الغرفة — دخول غرفة\nخروج — الخروج من الغرفة الحالية\nخروج اسم_الغرفة — الخروج من غرفة محددة\nغرفي — عرض الغرف التي يتواجد بها البوت\nmyrooms — نفس الأمر\n\ninv — دعوة أعضاء الغرفة الحالية\ninv اسم_الغرفة — دعوة أعضاء غرفة محددة\nدعوات — نفس أمر inv\ninvite — نفس أمر inv\ninvmsg نص — تغيير رسالة الدعوة\ni@اسم — دعوة مستخدم واحد\n\n📌 inv يعمل داخل الغرفة المطلوبة، ويتطلب رفع البوت أونر عند الحاجة.',
            '🏠 الغرف والترحيب — 2\n━━━━━━━━━━━━\nsay نص — إرسال نص داخل الغرفة\nقل نص — إرسال نص داخل الغرفة\n\n+sr@اسم_المستخدم@النص — إضافة رد/ترحيب مخصص (ماستر)\nsr@on — تشغيل الردود المخصصة\nsr@off — إيقاف الردود المخصصة\nswc+@اسم_الحساب@النص — إضافة ترحيب مخصص (ماستر)\nswc@on — تشغيل الترحيبات\nswc@off — إيقاف الترحيبات\n\n🛡️ حماية وتكرار الغرفة تُدار من صلاحيات الإدارة.',
        ],
    }


def _default_help_pages():
    """First section of each help page, kept for backward compatibility."""
    return {page: sections[0] for page, sections in _default_help_sections().items()}


def _help_sections_from_messages():
    # The six help pages are a fixed public contract. Older deployments may
    # still contain root/bot_data messages.json files with a mixed help_pages
    # format; never let those legacy files merge categories together.
    # The canonical categories are defined in _default_help_sections().
    return _default_help_sections()

def _help_pages_from_messages():
    defaults=_default_help_pages()
    data=_load_local_json(MESSAGES_FILE,{})
    raw=data.get("help_pages") if isinstance(data,dict) else None
    if isinstance(raw,list) and raw:
        pages={}
        for i,v in enumerate(raw,1):
            if isinstance(v,str) and v.strip():
                pages[i]=v.replace("\\n","\n")
        if pages: return pages
    return defaults

def _command_help(page=1):
    try: page=int(page)
    except Exception: page=1
    pages=_help_pages_from_messages()
    page=max(1,min(len(pages),page))
    return pages.get(page,_default_help_pages()[1])

# ------------------------------ Bot ----------------------

def _shape_name(text):
    """Convert the logical username into visual RTL order exactly once.

    The username is never translated, normalized, stripped of symbols, or
    otherwise altered.  Only the rendering order is changed so Arabic looks
    like the same copied text the user sees in Talkin Chat.
    """
    raw = str(text or "")
    if not raw:
        return ""
    # Pillow/Raqm already performs Arabic shaping and bidirectional layout.
    # Reshaping and applying bidi before Raqm would reverse the text twice.
    try:
        if PIL_AVAILABLE and features.check("raqm"):
            return raw
    except Exception:
        pass
    if arabic_reshaper is not None and get_display is not None and _has_arabic(raw):
        try:
            return get_display(arabic_reshaper.reshape(raw), base_dir="R")
        except Exception:
            pass
    return raw

_GIFT_FONT_CACHE = {}
_GLYPH_CACHE = {}
_FONT_CMAP_CACHE = {}

try:
    from fontTools.ttLib import TTFont
    _FONTTOOLS_OK = True
except Exception:
    TTFont = None
    _FONTTOOLS_OK = False

def _load_font(path, size):
    key=(str(path),int(size))
    if key not in _GIFT_FONT_CACHE:
        _GIFT_FONT_CACHE[key]=ImageFont.truetype(str(path),int(size))
    return _GIFT_FONT_CACHE[key]

def _font_cmap(path):
    """Return a real Unicode cmap so .notdef/tofu glyphs are never mistaken
    for supported characters.  This fixes square boxes for decorative Unicode.
    """
    key=str(path)
    if key in _FONT_CMAP_CACHE:
        return _FONT_CMAP_CACHE[key]
    cmap=set()
    if _FONTTOOLS_OK:
        try:
            ft=TTFont(key, lazy=True)
            for table in ft['cmap'].tables:
                cmap.update(table.cmap.keys())
            ft.close()
        except Exception:
            cmap=set()
    _FONT_CMAP_CACHE[key]=cmap
    return cmap

def _gift_font(text,size):
    # Main Arabic font.  Other scripts/symbols are chosen from real Unicode
    # coverage below; NotoSansArabic must not claim missing glyphs.
    candidates = [
        BASE_DIR/"assets"/"NotoSansArabic-SemiBold.ttf",
        BASE_DIR/"assets"/"Amiri-Bold.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-SemiBold.ttf"),
        BASE_DIR/"assets"/"DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return _load_font(path,size)
    raise RuntimeError("لم أجد خطًا صالحًا لرسم أسماء الهدايا")

def _fallback_font_paths():
    paths=[
        BASE_DIR/"assets"/"NotoSansArabic-SemiBold.ttf",
        BASE_DIR/"assets"/"Amiri-Bold.ttf",
        BASE_DIR/"assets"/"DejaVuSans.ttf",
        BASE_DIR/"assets"/"NotoSansSymbols2-Regular.ttf",
        BASE_DIR/"assets"/"NotoSansSymbols-Regular.ttf",
        BASE_DIR/"assets"/"Symbola.ttf",
        BASE_DIR/"assets"/"NotoSansEgyptianHieroglyphs-Regular.ttf",
        BASE_DIR/"assets"/"NotoMusic-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansArabic-SemiBold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansEgyptianHieroglyphs-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoMusic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    # Also inspect any extra font files already shipped inside the bot assets.
    try:
        for root in (BASE_DIR/"assets", Path("/usr/share/fonts")):
            if root.exists():
                for ext in ("*.ttf", "*.otf"):
                    for fp in root.rglob(ext):
                        paths.append(fp)
    except Exception:
        pass
    out=[]; seen=set()
    for p in paths:
        p=Path(p)
        if p.is_file() and str(p) not in seen:
            seen.add(str(p)); out.append(p)
    return out

def _fallback_fonts(size):
    out=[]
    for p in _fallback_font_paths():
        try:
            out.append(_load_font(p,size))
        except Exception:
            continue
    return out

def _font_has_glyph(font, ch):
    """Check Unicode cmap first; never accept a tofu/.notdef box as support."""
    try:
        path=getattr(font, 'path', None)
        if path:
            cmap=_font_cmap(path)
            if cmap:
                return ord(ch) in cmap
        # Compatibility fallback when fontTools is unavailable.
        mask=font.getmask(ch)
        return mask.getbbox() is not None and font.getlength(ch) > 0
    except Exception:
        return False

def _pick_font_for_char(base, fallbacks, ch):
    # Prefer the Arabic/main font only when its cmap really contains the glyph.
    if _font_has_glyph(base, ch):
        return base
    for font in fallbacks:
        if _font_has_glyph(font, ch):
            return font
    return None

def _draw_name_visual(draw, xy, raw_text, size, fill, stroke_width=2,
                      stroke_fill=(0,0,0,220), direction="ltr"):
    """Draw one username from the user's exact command/message text.

    Arabic is reshaped/bidi-ordered once.  Each Unicode code point is then
    rendered with a font that genuinely contains that code point.  This is
    what prevents boxes for names containing 𓆩♛𓆪 and musical symbols.
    """
    raw_text = str(raw_text or "")
    try:
        native_rtl = bool(PIL_AVAILABLE and features.check("raqm") and _has_arabic(raw_text))
    except Exception:
        native_rtl = False
    # Raqm expects logical Arabic text and performs shaping plus bidi itself.
    # Do not pre-reverse it, otherwise the generated card shows mirrored text.
    base_font = _gift_font(raw_text, int(size))
    native_complete = native_rtl and all(
        _font_has_glyph(base_font, ch) or unicodedata.category(ch).startswith("M")
        for ch in raw_text if not ch.isspace()
    )
    if native_complete:
        try:
            draw.text(xy, raw_text, font=base_font, fill=fill,
                      stroke_width=stroke_width, stroke_fill=stroke_fill,
                      direction="rtl", language="ar")
        except Exception:
            draw.text(xy, raw_text, font=base_font, fill=fill,
                      stroke_width=stroke_width, stroke_fill=stroke_fill)
        try:
            return xy[0] + draw.textlength(raw_text, font=base_font,
                                           direction="rtl", language="ar")
        except Exception:
            return xy[0] + base_font.getlength(raw_text)

    # Decorative names often mix Arabic with Egyptian glyphs, chess symbols,
    # musical symbols, and tatweel.  No single font contains all of them, so
    # shape/bidi the complete logical string once, then draw visual runs with
    # real fallback fonts. This avoids tofu squares without reversing twice.
    if _has_arabic(raw_text) and arabic_reshaper is not None and get_display is not None:
        try:
            # Keep the logical string and lay out its font runs from the
            # right edge to the left.  Using get_display here reverses the
            # already RTL name once more for mixed decorative usernames.
            logical = raw_text
        except Exception:
            logical = raw_text
    else:
        logical = raw_text
    visual = logical
    if not visual:
        return xy[0]
    base=_gift_font(visual,int(size))
    fallbacks=_fallback_fonts(int(size))

    # Keep combining marks attached to the preceding glyph's font where possible.
    runs=[]; cur_font=None; cur=[]
    unsupported=[]
    prev_font=None
    for ch in visual:
        font=_pick_font_for_char(base,fallbacks,ch)
        # Combining marks/variation selectors should follow the previous font.
        cat=unicodedata.category(ch)
        if font is None and prev_font is not None and cat.startswith("M"):
            font=prev_font
        if font is None:
            unsupported.append(ch)
            # Do not draw a fake square. The character is omitted only when no
            # installed/shipped font can actually render it.
            continue
        if cur_font is None or getattr(font,'path',None)==getattr(cur_font,'path',None):
            cur.append(ch)
        else:
            runs.append((cur_font,''.join(cur))); cur=[ch]
        cur_font=font; prev_font=font
    if cur:
        runs.append((cur_font,''.join(cur)))

    # Mixed decorative names need RTL run placement. Arabic runs are shaped
    # natively by Raqm; symbol runs use their fallback font and retain order.
    if _has_arabic(raw_text) and native_rtl:
        y = xy[1]
        widths=[]
        for font,run in runs:
            try:
                direction = "rtl" if _has_arabic(run) else "ltr"
                width = draw.textlength(run, font=font, direction=direction, language="ar" if direction == "rtl" else None)
            except Exception:
                width = font.getlength(run)
            widths.append(width)
        x_right = xy[0] + sum(widths)
        for (font,run), width in reversed(list(zip(runs, widths))):
            x_right -= width
            direction = "rtl" if _has_arabic(run) else "ltr"
            try:
                draw.text((x_right,y),run,font=font,fill=fill,stroke_width=stroke_width,
                          stroke_fill=stroke_fill,direction=direction,
                          language="ar" if direction == "rtl" else None)
            except Exception:
                draw.text((x_right,y),run,font=font,fill=fill,stroke_width=stroke_width,
                          stroke_fill=stroke_fill)
        return xy[0] + sum(widths)

    x,y=xy
    for font,run in runs:
        try:
            draw.text((x,y),run,font=font,fill=fill,stroke_width=stroke_width,
                      stroke_fill=stroke_fill,direction="ltr")
        except Exception:
            draw.text((x,y),run,font=font,fill=fill,stroke_width=stroke_width,
                      stroke_fill=stroke_fill)
        try:
            x += draw.textlength(run,font=font,direction="ltr")
        except Exception:
            x += font.getlength(run)
    if unsupported:
        try:
            # Keep a concise diagnostic in the log without exposing the full name.
            print("[GIFT-FONT] unsupported Unicode: " + " ".join(f"U+{ord(c):04X}" for c in sorted(set(unsupported))))
        except Exception:
            pass
    return x

def _draw_exact_text(draw, xy, raw_text, size, fill, stroke_width=2, stroke_fill=(0,0,0,220)):
    return _draw_name_visual(draw, xy, raw_text, size, fill, stroke_width, stroke_fill)

def _fit_crop(im,size):
    im=im.convert("RGB"); tw,th=size; scale=max(tw/im.width,th/im.height); nw,nh=max(tw,int(im.width*scale)),max(th,int(im.height*scale)); im=im.resize((nw,nh),Image.LANCZOS); left=max(0,(nw-tw)//2); top=max(0,(nh-th)//2); return im.crop((left,top,left+tw,top+th))

def _draw_centered(draw,center,raw_text,size,fill,max_width):
    return _draw_name_centered(draw, center, raw_text, size, fill, max_width)

def _visual_rtl_text(text):
    """Return logical text unchanged when Pillow/Raqm can shape Arabic.
    Older fallback renderers may need reshape+bidi.
    """
    text = str(text or "")
    try:
        if PIL_AVAILABLE and features.check("raqm"):
            return text
    except Exception:
        pass
    if arabic_reshaper is not None and get_display is not None:
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            pass
    return text

def _has_arabic(text):
    return any("\u0600" <= ch <= "\u06ff" or "\u0750" <= ch <= "\u077f" or "\u08a0" <= ch <= "\u08ff" for ch in str(text or ""))

def _draw_name_centered(draw, center, raw_text, size, fill, max_width):
    """Center the username using actual mixed-font glyph widths."""
    size=int(size)
    while size>14:
        visual=_shape_name(raw_text)
        base=_gift_font(visual,size)
        fallbacks=_fallback_fonts(size)
        width=0
        for ch in visual:
            font=_pick_font_for_char(base,fallbacks,ch)
            if font is None:
                continue
            try: width += draw.textlength(ch,font=font,direction='ltr')
            except Exception: width += font.getlength(ch)
        if width<=max_width:
            break
        size-=2
    visual=_shape_name(raw_text)
    base=_gift_font(visual,size)
    fallbacks=_fallback_fonts(size)
    width=0
    top=999999; bottom=-999999
    for ch in visual:
        font=_pick_font_for_char(base,fallbacks,ch)
        if font is None: continue
        try: width += draw.textlength(ch,font=font,direction='ltr')
        except Exception: width += font.getlength(ch)
        try:
            b=font.getbbox(ch)
            top=min(top,b[1]); bottom=max(bottom,b[3])
        except Exception:
            pass
    if top==999999:
        return
    x=center[0]-width/2
    y=center[1]-(bottom-top)/2-top
    _draw_name_visual(draw,(x,y),raw_text,size,fill,stroke_width=2,stroke_fill=(0,0,0,220))

def _visual_runs(text, size):
    # Kept for compatibility with older helpers.
    visual = _visual_rtl_text(_shape_name(text))
    base = _gift_font(visual, size)
    fallbacks = _fallback_fonts(size)
    runs=[]; cur_font=None; cur=[]
    for ch in visual:
        chosen = base if _font_has_glyph(base, ch) else next((f for f in fallbacks if _font_has_glyph(f, ch)), base)
        if cur_font is None or chosen is cur_font:
            cur.append(ch)
        else:
            runs.append((cur_font,''.join(cur))); cur=[ch]
        cur_font=chosen
    if cur: runs.append((cur_font,''.join(cur)))
    return runs

def _visual_text_width(draw, text, size):
    try:
        font=_gift_font(text,size)
        direction="rtl" if _has_arabic(text) else "ltr"
        box=draw.textbbox((0,0),str(text),font=font,direction=direction)
        return box[2]-box[0]
    except Exception:
        return sum(draw.textlength(run,font=font) for font,run in _visual_runs(text,size))

def _draw_exact_text(draw, xy, raw_text, size, fill, stroke_width=1, stroke_fill=(0,0,0,180)):
    return _draw_name_centered(draw, (xy[0], xy[1]+size/2), raw_text, size, fill, 10000)

def _draw_centered(draw, center, raw_text, size, fill, max_width):
    return _draw_name_centered(draw, center, raw_text, size, fill, max_width)


def _load_sender_avatar(photo_url, size=190):
    """Download a sender profile photo and crop it to a circular avatar."""
    if not photo_url or not photo_url.startswith(("http://", "https://")):
        return None
    try:
        r = requests.get(photo_url, headers={"User-Agent":"TalkinBot/22"}, timeout=3)
        if r.status_code != 200 or not r.content:
            return None
        from io import BytesIO
        av = Image.open(BytesIO(r.content)).convert("RGB")
        av = _fit_crop(av, (size,size)).convert("RGBA")
        mask = Image.new("L", (size,size), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((2,2,size-2,size-2), fill=255)
        out = Image.new("RGBA", (size,size), (0,0,0,0))
        out.paste(av, (0,0), mask)
        ring = ImageDraw.Draw(out)
        ring.ellipse((2,2,size-2,size-2), outline=(248,202,91,255), width=7)
        return out
    except Exception:
        return None


def render_gift_card(gift_id, sender_name, receiver_name, sender_photo_url="", receiver_photo_url=""):
    """Render the gift card exactly as the Talkin reference layout.

    Important:
    - The ORIGINAL gift artwork is used; no new gift picture is generated.
    - Sender/receiver avatars are OUTSIDE their own name rectangles, on the LEFT.
    - The name rectangles are wider to support long account names.
    - The gift artwork fills the card as much as possible without distortion.
    - The final card is rendered larger and sharpened only to compensate for
      the small source gift files.
    """
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow غير مثبت")

    sender_name = str(sender_name or "")
    receiver_name = str(receiver_name or "")

    files = [p for p in GIFT_IMAGE_FILES.get(str(gift_id), []) if p.is_file()]
    if not files:
        raise FileNotFoundError("صور الهدية غير موجودة داخل assets")

    # Always use one of the ORIGINAL gift assets from assets/.
    # Pick randomly so repeated gifts do not keep using the same variant.
    gift_path = random.choice(files)

    # Clean old generated gift cards from the project before creating the
    # current one.  The source artwork itself is NEVER generated or replaced.
    generated_dir = BASE_DIR / "generated_gifts"
    try:
        generated_dir.mkdir(parents=True, exist_ok=True)
        for old_card in generated_dir.iterdir():
            if old_card.is_file():
                try:
                    old_card.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    template_path = BASE_DIR / "assets" / "gift_template_elegant.png"
    if template_path.is_file():
        template = Image.open(template_path).convert("RGBA")
    else:
        template = Image.new("RGBA", (1239, 1270), (0, 0, 0, 0))

    # Work at a genuinely large final canvas.  Keep the template's original
    # aspect ratio so the frame is enlarged horizontally and vertically
    # without being stretched.
    target_w = 900
    target_h = max(1, round(target_w * template.height / template.width))
    template = template.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # The gift itself remains proportional.  Since the supplied gift artwork
    # is square, a center crop into the nearly-square card preserves its
    # important details instead of squeezing it.
    gift_src = Image.open(gift_path).convert("RGBA")
    image = _fit_crop(gift_src, (target_w, target_h)).convert("RGBA")
    image.alpha_composite(template)

    d = ImageDraw.Draw(image)
    w, h = image.size
    gold = (244, 196, 92, 255)
    panel = (10, 14, 28, 248)

    # Gift title.
    header = (int(w * .27), int(h * .052), int(w * .73), int(h * .162))
    d.rounded_rectangle(header, radius=30, fill=panel, outline=gold, width=4)
    gift_name = GIFT_CATALOG.get(str(gift_id), ("🎁", "هدية"))[1]
    _draw_centered(
        d,
        ((header[0] + header[2]) / 2, header[1] + (header[3] - header[1]) / 2),
        "هدية " + gift_name,
        32,
        (255, 222, 155, 255),
        header[2] - header[0] - 40,
    )

    # Two wider identity panels.
    # IMPORTANT: the profile photos are outside the panels, on their LEFT side.
    # This leaves the complete rectangle available for long account names.
    box_w = int(w * .73)
    box_h = int(h * .125)
    box_x = int(w * .22)
    top_y = int(h * .675)
    bottom_y = int(h * .815)

    for y in (top_y, bottom_y):
        d.rounded_rectangle(
            (box_x, y, box_x + box_w, y + box_h),
            radius=24,
            fill=panel,
            outline=gold,
            width=4,
        )

    avatar_size = 112
    avatar_x = max(8, box_x - avatar_size - 16)
    avatar_ys = (
        top_y + (box_h - avatar_size) // 2,
        bottom_y + (box_h - avatar_size) // 2,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        avatars = list(
            pool.map(
                lambda url: _load_sender_avatar(url, avatar_size),
                (sender_photo_url, receiver_photo_url),
            )
        )

    # The whole rectangle is available for text because the avatar is outside.
    # This is important for long usernames/accounts.
    text_center_x = box_x + box_w / 2
    text_max_w = box_w - 34

    for idx, (y, label, name) in enumerate(
        (
            (top_y, "المرسل", sender_name),
            (bottom_y, "المستلم", receiver_name),
        )
    ):
        avatar = avatars[idx]
        if avatar is not None:
            # Photo is deliberately outside the rectangle on the LEFT.
            image.alpha_composite(avatar, (int(avatar_x), int(avatar_ys[idx])))

        _draw_centered(
            d,
            (text_center_x, y + int(box_h * .27)),
            label,
            22,
            (255, 224, 165, 255),
            text_max_w,
        )

    sender_color = (126, 226, 255, 255)
    receiver_color = (255, 166, 218, 255)

    _draw_name_centered(
        d,
        (text_center_x, top_y + box_h * .68),
        sender_name,
        38,
        sender_color,
        text_max_w,
    )
    _draw_name_centered(
        d,
        (text_center_x, bottom_y + box_h * .68),
        receiver_name,
        38,
        receiver_color,
        text_max_w,
    )

    # A light unsharp mask improves the apparent clarity of the ORIGINAL
    # 280x280 gift artwork after enlargement; it does not invent a new image.
    try:
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    except Exception:
        pass

    out = BASE_DIR / "generated_gifts" / f"gift_{gift_id}_{uuid.uuid4().hex}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)

    rgb = image.convert("RGB")
    # Keep the large 900px card and use high JPEG quality.  There is no
    # artificial 95KB cap here because that cap was the reason the card was
    # being compressed too aggressively and losing visible detail.
    for quality in (94, 92, 90, 88, 86, 84, 82):
        rgb.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        if out.stat().st_size <= 180 * 1024:
            break

    return out


# ============================================================
# شبيه المستخدم: بحث تلقائي عن صورة من الويب وإرسالها للغرفة.
# لا ننشئ صورة جديدة؛ نستخدم صورة حقيقية من نتائج البحث العامة.
# ============================================================
LOOKALIKE_DIR = BASE_DIR / "generated_lookalikes"
LOOKALIKE_TIMEOUT = (5, 12)


def _extract_image_urls_from_bing(html_text):
    """Extract public image URLs from Bing Images HTML without extra packages."""
    text = html.unescape(str(html_text or ""))
    urls = []
    # Bing commonly embeds image metadata as murl in JSON-like attributes.
    patterns = (
        r'"murl"\s*:\s*"(https?://[^"\\]+)',
        r'&quot;murl&quot;\s*:\s*&quot;(https?://[^&]+)',
        r'"mediaurl"\s*:\s*"(https?://[^"\\]+)',
    )
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            try:
                url = bytes(match, "utf-8").decode("unicode_escape")
            except Exception:
                url = match
            url = url.replace('\\/', '/').strip()
            if url.startswith("https://") or url.startswith("http://"):
                if url not in urls:
                    urls.append(url)
    return urls


def _search_lookalike_image(query):
    """Search Bing Images and return the first downloadable image URL."""
    q = str(query or "").strip()
    if not q:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Android 10; Mobile) AppleWebKit/537.36 "
                      "Chrome/120.0 Mobile Safari/537.36",
        "Accept-Language": "ar,en;q=0.8",
    }
    try:
        r = requests.get(
            "https://www.bing.com/images/search",
            params={"q": q, "form": "HDRSC2", "first": "1"},
            headers=headers,
            timeout=LOOKALIKE_TIMEOUT,
        )
        r.raise_for_status()
        urls = _extract_image_urls_from_bing(r.text)
        return urls[0] if urls else None
    except Exception:
        return None


def _download_lookalike_image(image_url, target_name):
    """Download, validate, and lightly optimize a found image."""
    if not image_url:
        return None
    LOOKALIKE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(
            image_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
            timeout=LOOKALIKE_TIMEOUT,
            stream=True,
        )
        r.raise_for_status()
        data = r.content
        if len(data) > 8 * 1024 * 1024:
            return None
        if not PIL_AVAILABLE:
            return None
        from io import BytesIO
        img = Image.open(BytesIO(data)).convert("RGB")
        # Keep the found image recognizable; only normalize dimensions/file size.
        max_side = 1100
        if max(img.size) > max_side:
            scale = max_side / float(max(img.size))
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        out = LOOKALIKE_DIR / f"look_{uuid.uuid4().hex}.jpg"
        for quality in (92, 88, 84, 80, 76, 72):
            img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
            if out.stat().st_size <= 220 * 1024:
                break
        return out if out.is_file() else None
    except Exception:
        return None

class _MediaHandler(SimpleHTTPRequestHandler):
    def _resolve_target(self):
        path=unquote(urlparse(self.path).path)
        if path.startswith("/assets/"):
            rel=path[len("/assets/"):].lstrip("/"); root=ASSETS_DIR.resolve(); target=(ASSETS_DIR/rel).resolve()
        elif path.startswith("/gifts/"):
            rel=path[len("/gifts/"):].lstrip("/"); root=(BASE_DIR/"generated_gifts").resolve(); target=(BASE_DIR/"generated_gifts"/rel).resolve()
        elif path.startswith("/media/"):
            rel=path[len("/media/"):].lstrip("/"); root=(BASE_DIR/"generated_music").resolve(); target=(BASE_DIR/"generated_music"/rel).resolve()
        elif path.startswith("/lookalikes/"):
            rel=path[len("/lookalikes/"):].lstrip("/"); root=LOOKALIKE_DIR.resolve(); target=(LOOKALIKE_DIR/rel).resolve()
        else:
            return None
        if root not in target.parents or not target.is_file(): return None
        return target

    def _ctype(self,target):
        ctype,_=mimetypes.guess_type(str(target))
        return ctype or {
            ".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",".gif":"image/gif",
            ".mp3":"audio/mpeg",".m4a":"audio/mp4",".webm":"audio/webm",".ogg":"audio/ogg"
        }.get(target.suffix.lower(),"application/octet-stream")

    def _serve(self,head_only=False):
        target=self._resolve_target()
        if not target:
            self.send_error(404); return
        try:
            total=target.stat().st_size; start=0; end=total-1; status=200
            rh=self.headers.get("Range")
            if rh and rh.startswith("bytes="):
                spec=rh.split("=",1)[1].split(",",1)[0].strip(); a,_,b=spec.partition("-")
                if a: start=int(a); end=int(b) if b else total-1
                elif b:
                    length=int(b); start=max(0,total-length)
                if start>=total or end<start:
                    self.send_response(416); self.send_header("Content-Range",f"bytes */{total}"); self.end_headers(); return
                end=min(end,total-1); status=206
            length=end-start+1
            self.send_response(status)
            self.send_header("Content-Type",self._ctype(target))
            self.send_header("Accept-Ranges","bytes")
            self.send_header("Content-Length",str(length))
            if status==206: self.send_header("Content-Range",f"bytes {start}-{end}/{total}")
            self.send_header("Cache-Control","public,max-age=86400")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            if head_only: return
            with target.open("rb") as fh:
                fh.seek(start); remaining=length
                while remaining:
                    chunk=fh.read(min(1024*1024,remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining-=len(chunk)
        except Exception:
            try: self.send_error(404)
            except Exception: pass

    def do_HEAD(self): self._serve(True)
    def do_GET(self): self._serve(False)
    def log_message(self,fmt,*args):
        if DEBUG: print("[MEDIA] "+(fmt%args),flush=True)


def start_asset_server():
    if not ASSET_HTTP_ENABLED: return None
    try:
        (BASE_DIR/"generated_gifts").mkdir(parents=True,exist_ok=True); (BASE_DIR/"generated_music").mkdir(parents=True,exist_ok=True); LOOKALIKE_DIR.mkdir(parents=True,exist_ok=True)
        server=ThreadingHTTPServer(("0.0.0.0",ASSET_HTTP_PORT),_MediaHandler)
        threading.Thread(target=server.serve_forever,name="media-http",daemon=True).start()
        print(f"[MEDIA] HTTP server listening on :{ASSET_HTTP_PORT}",flush=True)
        return server
    except Exception as e:
        print("[MEDIA] HTTP server failed:",repr(e),flush=True); return None

class TalkinBot:
    def __init__(self):
        self.ws = None
        self.stop_event = threading.Event()
        self._silent_master_local = threading.local()
        self._master_reply_local = threading.local()
        self.http = requests.Session()
        self.port = DEFAULT_PORT
        self.room = GROUP_TO_JOIN
        self.auth = None
        self.last_error = None
        self.banned_words = set()
        self.moderation_enabled = AUTO_BAN_WORDS
        self.last_messages = defaultdict(list)
        # Per-room consecutive-message state. Protection can trigger when the
        # same user keeps sending messages OR when the same text is repeated,
        # including repeated text sent by different users.
        self._room_repeat_state = defaultdict(dict)
        # Talkin may deliver an inbound frame more than once around reconnects.
        # This cache prevents a duplicate event from executing a command again.
        self._incoming_seen = {}
        self._incoming_seen_lock = threading.Lock()
        self._management_command_seen = {}
        # Live room membership cache: username -> role.  This is updated by
        # occupants_list and by user_joined/user_left room events.
        self.room_users = defaultdict(dict)
        self.bot_room_roles = {}
        self._pending_inv_role_check = {}
        # Live profile photos learned from Talkin UserItem field 3.
        # username(casefold) -> public photo URL.
        self.user_photos = {}
        self.last_joined_room = None
        # Moderation commands are confirmed only after the server emits a
        # matching role_changed event.  Sending a packet is not proof that it
        # was accepted by the room server.
        self.pending_admin_actions = {}
        self.pending_admin_lock = threading.Lock()
        # Reaction/publish state must exist before any background music or
        # image-publish worker can write to it.
        self.reaction_targets = {}
        self.publish_pending = {}
        self.invite_pending = False
        self.invite_silent_master = False
        self.invite_room = ""
        self.invite_sent = set()
        self.invite_thread = None
        self.invite_lock = threading.Lock()
        self.invite_message_template = "🎁 لديك معجب مجهول 👥 في غرفة: {room}"
        self.known_rooms = set(_persistent_rooms())
        # Live rooms are session-only: unlike known_rooms (history on disk),
        # this set contains only rooms for which the current WebSocket session
        # has received a room/occupants response. It is cleared on disconnect.
        self.connected_rooms = set()
        # The offline private-service flow is active only while the master is
        # absent. Presence is updated from room membership and master messages.
        self.master_online = False
        self.master_last_seen = 0.0
        self._master_online_rooms = set()
        self._offline_support_sessions = {}
        self._offline_support_recent = {}
        # Keep rejected rooms tracked for history, but exclude them from
        # broadcasts and reconnect attempts until the master retries them.
        raw_blocked = _load_local_json(BLOCKED_ROOMS_FILE, [])
        if isinstance(raw_blocked, dict):
            raw_blocked = raw_blocked.get("rooms", [])
        self.blocked_rooms = {_norm_room(r) for r in (raw_blocked if isinstance(raw_blocked, list) else []) if _norm_room(r)}
        self._blocked_room_reasons = {}
        self._blocked_room_notices = set()
        self._pending_room_joins = {}
        if self.room:
            self.known_rooms.add(_norm_room(self.room))
        _save_persistent_rooms(self.known_rooms)
        self._join_lock = threading.Lock()
        self._last_join_sent = {}
        self._rejoin_attempts = defaultdict(int)
        self._last_reconnect = 0.0
        self._pending_reconnect_reason = ""
        self._had_connection = False
        # Do not flood the master when the server repeatedly reconnects.
        # Connection state is runtime-only and must not be stored in GitHub.
        self._last_connection_notice = 0.0
        self._connection_notice_cooldown = max(30.0, float(os.getenv("CONNECTION_NOTICE_COOLDOWN", "300")))
        # Reconnect progressively after transport failures instead of forcing
        # a visible leave/join cycle every fixed 10 seconds.
        self._reconnect_delay = 10.0
        self._reconnect_delay_max = max(30.0, float(os.getenv("RECONNECT_MAX_SECONDS", "120")))
        self._heartbeat_stop = None
        self._heartbeat_thread = None
        self.moderation_enabled, moderation_words = _load_moderation_config()
        self.banned_words = set(moderation_words)
        self.text_limit = max(80, int(os.getenv("TALKIN_TEXT_LIMIT", "180")))
        _ensure_replies_file()
        self.db = DatabaseBridge(self.log)
        self.db.sign_in()
        self.music_last = defaultdict(float)
        self.music_current = {}
        self._profile_status_lock = threading.Lock()
        self._profile_status_timer = None
        self._profile_status_token = 0
        self._profile_base_status = BOT_BASE_STATUS
        self._profile_current_status = BOT_BASE_STATUS
        self.music_lock = threading.Lock()
        # Mini-games: free-to-play, no points are deducted.
        self.game_lock = threading.Lock()
        self.game_cooldown = defaultdict(float)
        self.guess_games = {}
        self.help_pages = {}
        self.help_game_part = {}  # legacy alias used by older code
        self.help_page_part = {}
        # Global wager queues, crop timers, and fruit-match state.
        self.wager_waiting = {}
        # Global fixed-prize PvP queues: one open challenge per game name.
        self.fixed_game_waiting = {}
        raw_crops=_load_local_json(CROP_PLOTS_FILE,{})
        self.crop_plots = raw_crops if isinstance(raw_crops,dict) else {}
        self.fruit_games = {}
        # Auto replies and per-user custom welcome messages.
        self.auto_replies_enabled = True
        self.auto_replies = {}
        self.custom_welcome_enabled = True
        self.custom_welcomes = {}
        self._load_social_features()
        threading.Thread(target=self._crop_worker, name="crop-worker", daemon=True).start()
        self.invite_message_template = _message_template("invite", "default", "🎁 لديك معجب مجهول 👥 في غرفة: {room}")

    def _load_social_features(self):
        self.auto_replies_file = REPLIES_FILE
        self.custom_welcomes_file = DATA_DIR / "custom_welcomes.json"
        try:
            data = _ensure_replies_file()
            self.auto_replies_enabled = bool(data.get("auto_replies_enabled", True))
            raw = data.get("auto_replies", {})
            self.auto_replies = raw if isinstance(raw, dict) else {}
        except Exception:
            self.auto_replies_enabled, self.auto_replies = True, {}
        try:
            data = _load_local_json(self.custom_welcomes_file, {})
            self.custom_welcome_enabled = bool(data.get("enabled", True))
            raw = data.get("welcomes", {})
            self.custom_welcomes = raw if isinstance(raw, dict) else {}
        except Exception:
            self.custom_welcome_enabled, self.custom_welcomes = True, {}

    def _save_social_features(self):
        data = _ensure_replies_file()
        data["auto_replies_enabled"] = bool(self.auto_replies_enabled)
        data["auto_replies"] = self.auto_replies
        _save_local_json(self.auto_replies_file, data)
        _save_local_json(self.custom_welcomes_file, {"enabled": self.custom_welcome_enabled, "welcomes": self.custom_welcomes})

    def log(self, *args):
        if DEBUG:
            print(*args, flush=True)

    def report_master_error(self, context: str, error, room: str = ""):
        """Send the real diagnostic privately without exceeding Talkin's limit."""
        detail = " ".join(str(error or "خطأ غير معروف").split())
        location = f" | الغرفة: {room}" if room else ""
        message = f"❌ خطأ {context}{location}\nالتفاصيل: {detail}"
        self.log(f"[{context}]", repr(error))
        # Music/gift failures must remain visible in Railway Logs even when
        # DEBUG=0; the master also receives the complete diagnostic privately.
        print(f"[{context}] {detail}", flush=True)
        if BOT_MASTER and _norm_user(BOT_MASTER) != _norm_user(BOT_ID):
            try:
                self.send_private_text(BOT_MASTER, message)
            except Exception as notify_error:
                self.log("[MASTER-ERROR] failed:", repr(notify_error))

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

    def _start_heartbeat(self):
        """Keep the realtime socket alive while the room is idle.

        The server accepts RFC6455 control pings. The old loop only answered
        incoming pings, so an idle connection could be closed with code 1000.
        """
        self._stop_heartbeat()
        stop = threading.Event()
        self._heartbeat_stop = stop
        interval = max(10.0, float(os.getenv("WS_HEARTBEAT_SECONDS", "25")))

        def run():
            while not stop.wait(interval):
                ws = self.ws
                if not ws or not ws.sock:
                    return
                try:
                    ws.send_control(0x9, b"talkin-heartbeat")
                    self.log("[WS] heartbeat ping sent")
                except Exception as exc:
                    self.log("[WS] heartbeat failed:", repr(exc))
                    return

        self._heartbeat_thread = threading.Thread(target=run, name="ws-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        stop = self._heartbeat_stop
        if stop:
            stop.set()
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def _save_blocked_rooms(self):
        try:
            _save_local_json(BLOCKED_ROOMS_FILE, {"version": 1, "rooms": sorted(self.blocked_rooms)})
        except Exception as exc:
            self.log("[ROOM] blocked rooms save failed", repr(exc))

    def _mark_room_blocked(self, room: str, reason: str = ""):
        room = _norm_room(room)
        if not room:
            return
        self.blocked_rooms.add(room)
        if reason:
            self._blocked_room_reasons[room] = reason
        self.known_rooms = {r for r in self.known_rooms if _norm_room(r) != room}
        self.connected_rooms = {r for r in self.connected_rooms if _norm_room(r) != room}
        self.room_users.pop(room, None)
        _save_persistent_rooms(self.known_rooms)
        self._save_blocked_rooms()
        self.log("[ROOM] marked blocked/inaccessible:", room, reason)

    def _room_failure_message(self, room: str, event_type: str):
        labels = {
            "room_unauthorized_rejoin": "🚫 البوت محظور من الغرفة",
            "room_membership_required_rejoin": "🚫 الغرفة للأعضاء/تحتاج عضوية للبوت",
            "room_full_rejoin": "⚠️ الغرفة ممتلئة ولا يمكن للبوت الدخول",
            "room_wrong_password_rejoin": "🔐 الغرفة تحتاج كلمة مرور أو كلمة المرور غير صحيحة",
            "room_needs_password_rejoin": "🔐 الغرفة تحتاج كلمة مرور",
            "room_needs_captcha_rejoin": "🤖 الغرفة تطلب تحقق CAPTCHA ولا يمكن للبوت الدخول آلياً",
        }
        return labels.get(event_type, "❌ تعذر دخول البوت إلى الغرفة")

    def join_room(self, room: str, force: bool = False):
        """Join a room, allowing a previously-left room to be joined again.

        ``known_rooms`` is persistent history, while ``connected_rooms`` is the
        current WebSocket session. A room that is only in known_rooms is NOT
        considered currently joined; this is important after ``خروج``.
        """
        room = str(room or "").strip()
        if not room:
            return False
        if _norm_room(room) in getattr(self, "blocked_rooms", set()) and not force:
            self.log("[ROOM] join suppressed (bot is blocked):", room)
            return False
        known_norm = {_norm_room(r) for r in getattr(self, "known_rooms", set())}
        connected_norm = {_norm_room(r) for r in getattr(self, "connected_rooms", set())}
        already_known = _norm_room(room) in known_norm
        already_connected = _norm_room(room) in connected_norm
        # Being saved in tracked_rooms.json alone must never block a fresh join.
        if already_connected and not force:
            self.log("[ROOM] already connected:", room)
            return False
        now = time.time()
        with self._join_lock:
            last = self._last_join_sent.get(room, 0.0)
            if not force and now - last < float(os.getenv("JOIN_DEBOUNCE_SECONDS", "20")):
                self.log("[ROOM] join suppressed (debounce):", room)
                return False
            self._last_join_sent[room] = now
        self.log("[ROOM] joining", room)
        self._pending_room_joins[_norm_room(room)] = {"room": room, "started": time.time(), "requested_by": ""}
        self.send_query(encode_query("room_join", room=room, int_value=0, force_int_value=True))
        self.known_rooms.add(room)
        _save_persistent_rooms(self.known_rooms)
        self.request_room_occupants(room)
        return True

    def request_room_occupants(self, room: str):
        """Load and persist the complete room roster without a huge WebSocket frame.

        Supabase is used first because it can return the room members in small
        HTTP batches. Only when the database cannot provide the roster do we fall
        back to Talkin's occupants_list WebSocket response.
        """
        room = _norm_room(room)
        if not room:
            return False
        try:
            db_users = self.db.room_users(room) if getattr(self, "db", None) else []
        except Exception as exc:
            db_users = []
            self.log("[ROOM] DB roster refresh failed", room, repr(exc))
        if db_users:
            users_info = []
            for user in db_users:
                if not isinstance(user, dict):
                    continue
                username = str(user.get("username") or "").strip()
                if username and _norm_user(username) != _norm_user(BOT_ID):
                    users_info.append({
                        "username": username,
                        "role": str(user.get("role") or "none").strip().lower() or "none",
                        "user_id": str(user.get("user_id") or ""),
                    })
            if users_info:
                self.room_users[room] = {u["username"]: u.get("role", "none") for u in users_info}
                _remember_roster(room, users_info)
                self.last_joined_room = room
                self.log("[ROOM] complete roster saved", room, "users=", len(users_info))
                return True
        if not self.ws:
            return False
        try:
            self.send_query(encode_query(
                "room_admin", type_="occupants_list", room=room,
                to=BOT_ID, value="none"
            ))
            self.last_joined_room = room
            self.log("[ROOM] occupants refresh requested (WebSocket fallback)", room)
            return True
        except Exception as exc:
            self.log("[ROOM] occupants refresh failed", room, repr(exc))
            return False

    def leave_room(self, room: str):
        """Leave exactly one Talkin room using the APK's room_leave packet."""
        room = str(room or "").strip()
        if not room:
            return False
        self.send_query(encode_query("room_leave", room=room))
        with self._join_lock:
            self.known_rooms.discard(room)
            _save_persistent_rooms(self.known_rooms)
            self._last_join_sent.pop(room, None)
        self.room_users.pop(room, None)
        self.connected_rooms.discard(room)
        self.log("[ROOM] left", room)
        return True

    def leave_all_rooms(self):
        """Leave every currently tracked room; no room is automatically rejoined."""
        rooms = [r for r in self.known_rooms if str(r).strip()]
        for room in rooms:
            try:
                self.leave_room(room)
            except Exception as e:
                self.log("[ROOM] leave failed", room, repr(e))
        return rooms

    def _split_talkin_text(self, text: str, limit: int = None):
        """Compatibility helper: command menus use their own <=300 splitter."""
        text = str(text or "")
        return [text] if text else [""]

    def _send_text_packets(self, packet_type: str, text: str, **kwargs):
        # Normal replies remain one complete message. Only help menus use the
        # explicit line-based batching in _send_help_chunks below.
        payload = dict(kwargs)
        payload["type_"] = "text"
        payload["body"] = str(text or "")
        self.send_query(encode_query(packet_type, **payload))
        return True

    def _send_help_chunks(self, packet_type: str, text: str, limit: int = HELP_PACKET_MAX_CHARS, **kwargs):
        """Send help menus as ordered lists of at most ten lines."""
        text = str(text or "")
        if not text:
            return True
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        chunks=[]; current=""
        for line in lines:
            candidate = line if not current else current + "\n" + line
            if len(current.splitlines()) < HELP_LINES_PER_MESSAGE and len(candidate) <= limit:
                current=candidate
            else:
                if current:
                    chunks.append(current)
                current=line
        if current: chunks.append(current)
        for chunk in chunks:
            payload=dict(kwargs); payload["type_"]="text"; payload["body"]=chunk
            self.send_query(encode_query(packet_type, **payload))
        return True

    def _active_rooms(self):
        rooms = {str(r).strip() for r in getattr(self, "known_rooms", set()) if str(r).strip()}
        if self.room:
            rooms.add(str(self.room).strip())
        rooms.update(str(r).strip() for r in self.room_users.keys() if str(r).strip())
        rooms.update(str(r).strip() for r in getattr(self, "connected_rooms", set()) if str(r).strip())
        blocked = {_norm_room(r) for r in getattr(self, "blocked_rooms", set())}
        return sorted(r for r in rooms if _norm_room(r) not in blocked)

    def broadcast_all_rooms(self, text: str):
        """Send one public game announcement to every room currently tracked by the bot."""
        sent = 0
        for target_room in self._active_rooms():
            try:
                self.send_room_text(target_room, text)
                sent += 1
            except Exception as exc:
                self.log("[BROADCAST] failed", target_room, repr(exc))
        return sent

    def send_room_text(self, room: str, text: str):
        if getattr(self._master_reply_local, "tracking", False):
            self._master_reply_local.replied = True
        if getattr(self._silent_master_local, "active", False):
            return True
        return self._send_text_packets("room_message", text, room=room)

    def send_room_lines(self, room: str, lines):
        for line in lines:
            if line is not None:
                self.send_room_text(room, str(line))
        return True

    def send_admin(self, room: str, target: str, operation: str):
        """Execute room moderation directly over TalkinChat's native room_admin query.

        The deployment log confirms the native result states:
          kick -> role_changed with role "kicked", followed by user_left
          ban  -> role_changed with role "outcast"
        Therefore kick/ban must NOT depend on Supabase, config.json, or a DB RPC.
        """
        room = str(room or "").strip()
        target = str(target or "").strip().lstrip("@")
        if not room:
            raise ValueError("room is required")
        if not target:
            raise ValueError("target is required")

        if operation == "kick":
            self.log(f"[MOD] native kick room={room} target=@{target}")
            payload = encode_query(
                "room_admin",
                type_="kick",
                room=room,
                to=target,
                value="none",
            )
            return self.send_query(payload)

        if operation == "ban":
            # A room ban is represented by the same role transition that the
            # client reports in `role_changed`.  `ban_ip` was accepted by the
            # gateway in some versions but did not change room membership.
            self.log(f"[MOD] room outcast room={room} target=@{target}")
            payload = encode_query(
                "room_admin",
                type_="change_role",
                room=room,
                to=target,
                value="outcast",
            )
            return self.send_query(payload)

        role_map = {
            "outcast": "outcast",
            "admin": "admin",
            "member": "member",
            "owner": "owner",
            "none": "none",
        }
        if operation in role_map:
            return self.send_query(
                encode_query(
                    "room_admin",
                    type_="change_role",
                    room=room,
                    to=target,
                    value=role_map[operation],
                )
            )
        raise ValueError("Unknown admin operation: " + operation)

    def request_admin_action(self, room: str, target: str, operation: str, requester: str, announce_room: bool = False):
        """Send moderation request and report success only after server confirmation."""
        role_by_operation = {
            "kick": "kicked", "ban": "outcast", "member": "member",
            "admin": "admin", "owner": "owner",
        }
        expected_role = role_by_operation.get(operation)
        if not expected_role:
            raise ValueError("Unknown admin operation: " + operation)
        room = str(room or "").strip()
        target = str(target or "").strip().lstrip("@")
        requester = str(requester or "").strip()
        try:
            self.send_admin(room, target, operation)
        except Exception as exc:
            self.log(f"[MOD] request failed room={room} target=@{target}: {exc!r}")
            if requester and not _is_master_name(requester):
                self.send_private_text(requester, f"❌ تعذر إرسال أمر الإدارة إلى الخادم: {exc}")
            return False
        key = (room.casefold(), target.casefold(), expected_role)
        with self.pending_admin_lock:
            self.pending_admin_actions[key] = {
                "room": room, "target": target, "role": expected_role,
                "requester": requester, "created_at": time.time(), "announced": False,
                "announce_room": bool(announce_room),
            }
        labels = {
            "kicked": "طرد",
            "outcast": "حظر",
            "member": "فك الحظر",
            "admin": "تعيين مشرف",
            "owner": "تعيين أونر",
        }
        # Master moderation commands are intentionally silent in both room and private chat.
        self.log(f"[MOD] awaiting server confirmation room={room} target=@{target} role={expected_role}")
        threading.Thread(
            target=self._admin_confirmation_timeout,
            args=(key,), daemon=True, name="admin-confirmation-timeout",
        ).start()
        return True

    def _admin_confirmation_timeout(self, key):
        time.sleep(float(os.getenv("ADMIN_CONFIRMATION_TIMEOUT", "8")))
        with self.pending_admin_lock:
            pending = self.pending_admin_actions.pop(key, None)
        # A timeout is intentionally silent.  Talkin may apply the role
        # change while delaying or omitting the matching event; showing a
        # failure message after a successful native room notification is
        # misleading.  Only role_changed below emits a success message.
        if pending:
            self.log(f"[MOD] confirmation timeout room={pending['room']} target=@{pending['target']}")

    def ack(self, uid: str):
        if uid:
            self.send_query(encode_query("ack_msg", uid=uid))

    def send_private_text(self, username: str, text: str):
        """Send the complete private text in safe sequential chunks.

        The private chat may display long reports, but one oversized protobuf
        can make Talkin close the entire WebSocket with code 1009. Chunking
        preserves every character while keeping each packet below the safe
        room/server limit.
        """
        tracking = getattr(self._master_reply_local, "tracking", False)
        # Management responses addressed to the master follow the channel
        # where the command arrived: room command -> room reply, private
        # command -> private reply. Notifications addressed to other users
        # remain private and are not rerouted.
        if (tracking and not getattr(self._master_reply_local, "command_private", True)
                and _norm_user(username) == _norm_user(getattr(self._master_reply_local, "command_sender", ""))
                and not getattr(self._master_reply_local, "rerouting", False)):
            self._master_reply_local.rerouting = True
            try:
                return self.send_room_text(getattr(self._master_reply_local, "command_room", ""), text)
            finally:
                self._master_reply_local.rerouting = False
        if tracking:
            self._master_reply_local.replied = True
            self._master_reply_local.private_replied = True
        if getattr(self._silent_master_local, "active", False):
            return True
        username = str(username or "").strip()
        if not username or username == BOT_ID:
            return False
        return self._send_text_packets("chat_message", text, to=username)

    def send_private_media(self, username: str, media_url: str, media_type: str, duration: int = 0):
        """Send audio/image back to the private-chat sender."""
        return self.send_query(encode_query(
            "chat_message", type_=media_type, to=username, url=media_url,
            length=str(max(0, int(duration or 0))) if media_type == "audio" else None
        ))

    def _master_is_online(self):
        """Return the latest presence state known by this bot connection."""
        return bool(getattr(self, "master_online", False))

    def _master_service_menu(self, username: str):
        """Greeting/menu shown once per private conversation with the master."""
        username = str(username or "").strip().lstrip("@")
        return (
            f"مرحبا عزيزي @{username}\n"
            "الماستر نائم الآن\n"
            "كيف يمكنني خدمتك؟\n"
            "1️⃣ توثيق\n"
            "2️⃣ شكاوي أو مقترحات\n"
            "3️⃣ توثيق لحساب اخر\n"
            "ارسل رقم 1 او 2 او 3"
        )

    def _offline_support_menu(self, username: str = ""):
        return self._master_service_menu(username)

    def _handle_master_process_command(self, sender: str, body: str, is_private: bool = False):
        """Control the standalone master account from the primary bot private chat."""
        if not is_private or not _is_master_name(sender):
            return False
        low = str(body or "").strip().casefold()
        if low in ("تشغيل الماستر", "تشغيل الماستر@", "start master", "master on"):
            ok, msg = _start_master_process()
            self.send_private_text(sender, msg)
            return True
        if low in ("ايقاف الماستر", "إيقاف الماستر", "ايقاف الماستر@", "إيقاف الماستر@", "stop master", "master off"):
            ok, msg = _stop_master_process()
            self.send_private_text(sender, msg)
            return True
        if low in ("حالة الماستر", "حاله الماستر", "master status"):
            self.send_private_text(sender, "🟢 الماستر يعمل." if _master_process_running() else "🔴 الماستر متوقف.")
            return True
        return False

    def _handle_offline_master_service(self, sender: str, body: str):
        """Handle private service requests only while BOT_MASTER is absent."""
        sender = str(sender or "").strip()
        body = str(body or "").strip()
        if not sender or _norm_user(sender) in {_norm_user(BOT_MASTER), _norm_user(BOT_ID)}:
            return False
        sessions = getattr(self, "_offline_support_sessions", None)
        if not isinstance(sessions, dict):
            sessions = {}
            self._offline_support_sessions = sessions
        recent = getattr(self, "_offline_support_recent", None)
        if not isinstance(recent, dict):
            recent = {}
            self._offline_support_recent = recent
        key = _norm_user(sender)
        state = sessions.get(key, "")
        low = body.casefold()

        # Talkin may deliver the same private frame more than once. Ignore an
        # identical sender/message pair briefly so menus and acknowledgements
        # are never duplicated.
        signature = (key, body)
        now = time.time()
        if now - float(recent.get(signature, 0.0) or 0.0) < 15:
            return True
        recent[signature] = now

        if not state:
            sessions[key] = "menu"
            self.send_private_text(sender, self._master_service_menu(sender))
            return True

        if state == "complaint":
            if not body:
                self.send_private_text(sender, "❌ أرسل نص الشكوى أو المقترح.")
                return True
            if MASTER_SUPPORT_USERNAME:
                self.send_private_text(MASTER_SUPPORT_USERNAME, f"📩 شكوى أو مقترح من @{sender}:\n{body}")
            else:
                self.log("[OFFLINE-SUPPORT] MASTER_SUPPORT_USERNAME is not configured")
            self.send_private_text(sender, "✅ سيتم إبلاغ الإدارة ونبلغك قريباً.")
            sessions.pop(key, None)
            return True

        if low in ("2", "🟦2", "🟦2️⃣", "2️⃣", "شكوى", "شكاوي", "شكاوى", "مقترحات", "اقتراح"):
            sessions[key] = "complaint"
            self.send_private_text(sender, "✍️ تفضل أرسل الشكوى أو المقترح الآن.")
            return True

        if low in ("1", "🟦1", "🟦1️⃣", "1️⃣", "توثيق", "وثق", "التوثيق"):
            # The primary bot NEVER grants verification while the master is
            # away. Verification is an action performed by the master account.
            # Forward the request to the master/support account and leave the
            # verified_users store untouched until the master approves it.
            if MASTER_SUPPORT_USERNAME:
                self.send_private_text(
                    MASTER_SUPPORT_USERNAME,
                    f"📋 طلب توثيق جديد من @{sender}.\n"
                    f"يرجى توثيقه من حساب الماستر باستخدام: vi@{sender}"
                )
            sessions.pop(key, None)
            self.send_private_text(sender, "📩 تم إرسال طلب التوثيق إلى الماستر. سيتم توثيقك بعد موافقته.")
            return True

        # Do not repeat the menu for an unrecognized follow-up message.
        return True

    def _relay_private_to_owner(self, sender: str, body: str, media_url: str = ""):
        """Mirror master-account private traffic to the configured owner.

        MASTER_SUPPORT_USERNAME is the single owner/support account used for
        complaints, so it also receives private messages while the master
        service is running. Exclude the owner and local bot accounts to avoid
        forwarding loops and internal control chatter.
        """
        owner = str(MASTER_SUPPORT_USERNAME or "").strip()
        sender = str(sender or "").strip()
        if not owner or not sender:
            return False
        excluded = {_norm_user(owner), _norm_user(BOT_ID), _norm_user(PRIMARY_BOT_ID)}
        if _norm_user(sender) in excluded:
            return False
        parts = [f"📨 رسالة خاصة من @{sender}:"]
        if body:
            parts.append(str(body))
        if media_url:
            parts.append(f"📎 وسائط: {media_url}")
        return bool(self.send_private_text(owner, "\n".join(parts)))

    def _handle_master_account_service(self, sender: str, body: str):
        """Private auto-service handled by the master account itself.

        Verification is requested through the primary bot with ``vi@username``.
        The primary bot's reply is then relayed privately to the original user.
        Duplicate Talkin frames are ignored briefly so a single choice produces
        a single reply.
        """
        if not MASTER_SERVICE_ENABLED:
            return False
        sender = str(sender or "").strip()
        body = str(body or "").strip()
        if not sender:
            return False

        sessions = getattr(self, "_master_service_sessions", None)
        if not isinstance(sessions, dict):
            sessions = {}
            self._master_service_sessions = sessions
        pending = getattr(self, "_master_verify_pending", None)
        if not isinstance(pending, dict):
            pending = {}
            self._master_verify_pending = pending
        recent = getattr(self, "_master_service_recent", None)
        if not isinstance(recent, dict):
            recent = {}
            self._master_service_recent = recent

        key = _norm_user(sender)
        low = body.casefold()
        signature = (key, body)
        now = time.time()
        if now - float(recent.get(signature, 0.0) or 0.0) < 15:
            return True
        recent[signature] = now
        # Prevent this cache from growing forever.
        if len(recent) > 500:
            cutoff = now - 30
            for k, ts in list(recent.items()):
                if ts < cutoff:
                    recent.pop(k, None)

        # Result returned by the primary bot after the master sent vi@target.
        # Do not depend on extracting the username with a restrictive regex:
        # Talkin usernames can contain unusual Unicode/combining characters.
        if PRIMARY_BOT_ID and _norm_user(sender) == _norm_user(PRIMARY_BOT_ID):
            body_low = body.casefold()
            matched_key = None
            matched_info = None
            for target_key, info in list(pending.items()):
                target = str(info.get("target", "") or "").strip()
                if target and _norm_user(target) in _norm_user(body):
                    matched_key = target_key
                    matched_info = info
                    break
            # Fallback for normal "@username" replies when target matching is
            # not possible for a particular Unicode username.
            if matched_info is None and pending:
                m = re.search(r"@(.+?)(?:\.|\n|$)", body, re.S)
                if m:
                    candidate = m.group(1).strip()
                    for target_key, info in list(pending.items()):
                        target = str(info.get("target", "") or "").strip()
                        if _norm_user(candidate) == _norm_user(target):
                            matched_key = target_key
                            matched_info = info
                            break

            if matched_info is not None:
                pending.pop(matched_key, None)
                requester = str(matched_info.get("requester", "") or "").strip()
                target = str(matched_info.get("target", "") or "").strip().lstrip("@")
                if requester:
                    if "موثق سابق" in body_low or "توثيق عادي بالفعل" in body_low:
                        reply = f"⚠️ @{target} حسابه موثق سابقا."
                    elif "vip" in body_low or "توثيق VIP بالفعل" in body_low:
                        reply = f"⚠️ @{target} لديه توثيق VIP بالفعل."
                    elif "تم توثيق" in body_low:
                        reply = f"✅ تم توثيق @{target} بنجاح.\n🎉 يمكنك الآن استخدام أوامر البوت."
                    else:
                        reply = body
                    # Final notification is always sent by the master account
                    # directly to the verified user, not to a room.
                    self.send_private_text(requester, reply)
                    owner = str(MASTER_SUPPORT_USERNAME or "").strip()
                    if owner and _norm_user(owner) not in {_norm_user(requester), _norm_user(BOT_ID)}:
                        self.send_private_text(owner, f"✅ تم توثيق @{target} بنجاح.\n📩 مقدم الطلب: @{requester}")
                return True
            # Any private message from the primary bot is internal; never show
            # it to other users and never fall through to the service menu.
            return True

        if _norm_user(sender) == _norm_user(BOT_ID):
            return False

        # Option 1: verify the sender's own account.
        if low in ("1", "🟦1", "🟦1️⃣", "1️⃣", "توثيق", "وثق", "التوثيق"):
            target_bot = PRIMARY_BOT_ID.strip()
            if not target_bot:
                self.send_private_text(sender, "❌ لم يتم ضبط PRIMARY_BOT_ID للبوت الأساسي.")
                return True
            target_key = _norm_user(sender)
            pending[target_key] = {
                "requester": sender,
                "target": sender,
                "created_at": now,
            }
            if not self.send_private_text(target_bot, f"vi@{sender}"):
                pending.pop(target_key, None)
                self.send_private_text(sender, "❌ تعذر تنفيذ التوثيق الآن، حاول مرة أخرى.")
            return True

        # Option 2: complaint/suggestion. One prompt only; the actual complaint
        # is sent privately to MASTER_SUPPORT_USERNAME and not to the master
        # account unless that username is explicitly the same account.
        if low in ("2", "🟦2", "🟦2️⃣", "2️⃣", "شكوى", "شكاوي", "شكاوى", "مقترحات", "اقتراح"):
            sessions[key] = "complaint"
            self.send_private_text(sender, "✍️ تفضل أرسل الشكوى أو المقترح الآن.")
            return True

        if sessions.get(key) == "complaint":
            if not body:
                # Empty frames are silently ignored; do not spam the user.
                return True
            support = str(MASTER_SUPPORT_USERNAME or "").strip()
            sent = False
            if support and _norm_user(support) != _norm_user(BOT_ID):
                sent = bool(self.send_private_text(
                    support,
                    f"📩 شكوى أو مقترح من @{sender}:\n{body}"
                ))
            sessions.pop(key, None)
            if sent:
                self.send_private_text(sender, "✅ تم استلام الشكوى أو المقترح.")
            else:
                self.send_private_text(sender, "❌ تعذر إرسال الشكوى أو المقترح للإدارة الآن.")
            return True

        # Option 3: verify another account on behalf of the requester.
        if low in ("3", "🟦3", "🟦3️⃣", "3️⃣", "توثيق لحساب اخر", "توثيق لحساب آخر", "وثق حساب اخر", "وثق حساب آخر"):
            sessions[key] = "verify_other"
            self.send_private_text(sender, "👤 أرسل اسم المستخدم الذي تريد توثيقه الآن.")
            return True

        if sessions.get(key) == "verify_other":
            target = body.strip().lstrip("@").split()[0] if body else ""
            if not target:
                # Empty frames are silently ignored; do not repeat the prompt.
                return True
            target_bot = PRIMARY_BOT_ID.strip()
            if not target_bot:
                sessions.pop(key, None)
                self.send_private_text(sender, "❌ لم يتم ضبط PRIMARY_BOT_ID للبوت الأساسي.")
                return True
            target_key = _norm_user(target)
            pending[target_key] = {
                "requester": sender,
                "target": target,
                "created_at": now,
            }
            if not self.send_private_text(target_bot, f"vi@{target}"):
                pending.pop(target_key, None)
                self.send_private_text(sender, "❌ تعذر تنفيذ التوثيق الآن، حاول مرة أخرى.")
                return True
            sessions.pop(key, None)
            return True

        # First message only: show the menu. Do not repeat it on every message.
        if not sessions.get(key):
            sessions[key] = "menu"
            self.send_private_text(sender, self._master_service_menu(sender))
        return True

    def reply_text(self, room: str, text: str, private_to: str = ""):
        return self.send_private_text(private_to, text) if private_to else self.send_room_text(room, text)

    def _bot_room_role(self, room):
        room = str(room or "").strip()
        role = str(getattr(self, "bot_room_roles", {}).get(_norm_room(room), "") or "").casefold().strip()
        if role:
            return role
        live = getattr(self, "room_users", {}).get(room, {}) or {}
        for username, value in live.items():
            if _norm_user(username) == _norm_user(BOT_ID):
                return str(value or "").casefold().strip()
        return ""

    def _inv_bot_owner_allowed(self, room):
        role = self._bot_room_role(room)
        if role in {"owner", "creator", "room_owner", "room_creator"}:
            return True
        if role in {"admin", "moderator", "mod", "member", "user", "none"}:
            return False
        # Unknown role: ask the server for a fresh occupants list; the result
        # handler will complete the check and continue the invitation flow.
        try:
            self.send_query(encode_query("room_admin", type_="occupants_list", room=room, to=BOT_ID, value="none"))
            return None
        except Exception as exc:
            self.log("[INV] bot-role refresh failed", room, repr(exc))
            return False

    def request_occupants(self, room: str = "", silent_master: bool = False, response_room: str = "", response_to: str = ""):

        """Load invitation candidates ONLY from the room specified by inv.

        The source roster is restricted to that single room.  This prevents
        inv issued in one room from inviting users saved from other rooms.
        Owners, admins and normal members of the selected room are all eligible.
        """
        with self.invite_lock:
            if self.invite_pending:
                msg = "⏳ ما زلت أجمع معلومات الغرف، انتظر حتى تكتمل العملية."
                if response_room:
                    self.send_room_text(response_room, msg)
                elif response_to:
                    self.send_private_text(response_to, msg)
                else:
                    self.send_private_text(BOT_MASTER, msg)
                return
            self.invite_pending = True
            self.invite_silent_master = bool(silent_master)
            self.invite_room = str(room or self.room or "").strip()
            self.invite_sent.clear()

        command_room = self.invite_room
        response_room = str(response_room or "").strip()
        response_to = str(response_to or "").strip()
        # Keep the destination available to the async invite worker even when
        # users are loaded immediately from the persistent/DB roster.
        self._inv_response_room = response_room
        self._inv_response_to = response_to
        # IMPORTANT: invitations are scoped to the room where inv was requested.
        # Never merge the persistent rosters of the bot's other rooms.
        active_rooms = [command_room] if command_room else []
        self.log("[INV] loading users ONLY from requested room:", active_rooms)
        try:
            progress = (
                f"⏳ جاري جمع أعضاء الغرفة المطلوبة فقط...\n"
                f"📌 نص الدعوة سيكون باسم الغرفة التي نُفّذ فيها inv: {command_room}"
            )
            if response_room:
                self.send_room_text(response_room, progress)
            elif response_to:
                self.send_private_text(response_to, progress)
            else:
                self.send_private_text(BOT_MASTER, progress)
        except Exception as e:
            self.log("[INV] progress message failed:", repr(e))

        # PRIMARY SOURCE: database room_members contains the complete membership,
        # including users who are currently offline. Query ONLY this requested room.
        all_users = []
        seen = set()
        room_counts = {}
        for source_room in active_rooms:
            try:
                db_users = self.db.room_users(source_room)
            except Exception as exc:
                db_users = []
                self.log("[INV] DB room roster failed:", source_room, repr(exc))
            room_counts[source_room] = len(db_users or [])
            for u in db_users or []:
                username = str(u.get("username") or "").strip() if isinstance(u, dict) else ""
                if not username or _norm_user(username) == _norm_user(BOT_ID):
                    continue
                key = _norm_user(username)
                if key not in seen:
                    seen.add(key)
                    all_users.append(username)

        if all_users:
            self.log(f"[INV] COMPLETE ROOM ROSTER: room={command_room} total_members={len(all_users)} counts={room_counts} (offline included)")
            self.process_occupants_for_invite({
                "db_users": [{"username": u} for u in all_users],
                "source_rooms": active_rooms,
            })
            return

        # If the DB roster is unavailable/empty, use the saved roster for THIS
        # room only. It can contain offline users from an earlier full roster.
        for source_room in active_rooms:
            saved_users = _persistent_roster_users(source_room)
            room_counts[source_room] = max(room_counts.get(source_room, 0), len(saved_users))
            for username in saved_users:
                key = _norm_user(username)
                if key and key not in seen:
                    seen.add(key)
                    all_users.append(username)

        if all_users:
            self.log(f"[INV] SAVED ROOM ROSTER: room={command_room} total_members={len(all_users)}")
            self.process_occupants_for_invite({
                "db_users": [{"username": u} for u in all_users],
                "source_rooms": active_rooms,
            })
            return

        # Last fallback: request the server roster for the single requested room.
        self._inv_expected_rooms = set(active_rooms)
        self._inv_live_users = []
        self._inv_live_seen = set()
        self._inv_command_room = command_room
        self._inv_response_room = response_room
        self._inv_response_to = response_to
        if not active_rooms:
            with self.invite_lock:
                self.invite_pending = False
                self.invite_silent_master = False
            msg = "⚠️ لا توجد غرف نشطة حالياً. استخدم: دخول@اسم_الغرفة"
            if response_room:
                self.send_room_text(response_room, msg)
            elif response_to:
                self.send_private_text(response_to, msg)
            else:
                self.send_private_text(BOT_MASTER, msg)
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
                self.invite_silent_master = False

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

    def send_private_invite(self, username: str, room: str, inviter: str = ""):
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
            text = text.format(sender=(inviter or INVITE_SENDER_NAME), room=room, username=username)
        except Exception:
            text = f"🎁 لديك معجب مجهول 👥 في غرفة: {room}"
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
                photo = first_text(uf, 3).strip()
                status = first_text(uf, 4).strip()
                if username:
                    users.append({"username": username, "role": role or "none",
                                  "user_id": user_id, "online": online, "photo": photo,
                                  "status": status})
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
        silent_master = bool(self.invite_silent_master)
        response_room = str(getattr(self, "_inv_response_room", "") or "").strip()
        response_to = str(getattr(self, "_inv_response_to", "") or "").strip()
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
            if not silent_master:
                try:
                    if count == 0:
                        msg = (
                            f"⚠️ لم تُرسل أي دعوة. DB client={'نعم' if self.db.client else 'لا'} | "
                            f"Supabase room_id={self.db.last_room_id or 'غير موجود'} | "
                            f"room_members={self.db.last_member_count} | profiles={self.db.last_profile_count} | "
                            f"آخر خطأ={self.db.last_error or 'راجع سجل البوت'}"
                        )
                        if response_room:
                            self.send_room_text(response_room, msg)
                        elif response_to:
                            self.send_private_text(response_to, msg)
                        else:
                            self.send_private_text(BOT_MASTER, msg)
                except Exception:
                    pass
                try:
                    msg = (
                        f"✅ تم جمع معلومات الغرفة. عدد المستخدمين: {len(usernames)}\n"
                        f"📨 تم إرسال الدعوة العادية على الخاص إلى: {count} مستخدم."
                    )
                    if response_room:
                        self.send_room_text(response_room, msg)
                    elif response_to:
                        self.send_private_text(response_to, msg)
                    else:
                        self.send_private_text(BOT_MASTER, msg)
                except Exception as e:
                    self.log("[INV] final result failed:", repr(e))
        finally:
            with self.invite_lock:
                self.invite_pending = False
                self.invite_silent_master = False

    def _cache_user_photos_from_result(self, result):
        """Cache Talkin profile photo URLs from any occupants/users response."""
        try:
            for user in (result.get("users") or []):
                if not isinstance(user, dict):
                    continue
                username = str(user.get(1, "") or "").strip()
                photo = str(user.get(3, "") or "").strip()
                status = str(user.get(4, "") or "").strip()
                if username and username.casefold() == BOT_ID.casefold() and status:
                    with self._profile_status_lock:
                        self._profile_current_status = status
                        if self._profile_status_timer is None and not BOT_BASE_STATUS:
                            self._profile_base_status = status
                if username and photo and username != BOT_ID and photo.startswith(("http://", "https://")):
                    self.user_photos[username.casefold()] = photo
            for user in self._users_from_room_admin(result.get("room_admin") or {}):
                username = str(user.get("username") or "").strip()
                photo = str(user.get("photo") or "").strip()
                status = str(user.get("status") or "").strip()
                if username and username.casefold() == BOT_ID.casefold() and status:
                    with self._profile_status_lock:
                        self._profile_current_status = status
                        if self._profile_status_timer is None and not BOT_BASE_STATUS:
                            self._profile_base_status = status
                if username and photo and photo.startswith(("http://", "https://")):
                    self.user_photos[username.casefold()] = photo
        except Exception as exc:
            self.log("[GIFT] photo cache failed:", repr(exc))

    def _lookup_profile_photo(self, username):
        """Best-effort profile-photo lookup for a gift receiver not in cache."""
        username = str(username or "").strip().lstrip("@").casefold()
        if not username or not getattr(self.db, "client", None):
            return ""
        try:
            response = (self.db.client.table("profiles").select("*")
                        .eq("username", username).limit(1).execute())
            rows = getattr(response, "data", None) or []
            if rows:
                row = rows[0] if isinstance(rows[0], dict) else {}
                photo = next((str(row.get(key) or "").strip() for key in
                              ("photo_url", "photo", "avatar_url", "avatar", "image_url")
                              if str(row.get(key) or "").strip().startswith(("http://", "https://"))), "")
                if photo:
                    self.user_photos[username] = photo
                    return photo
        except Exception as exc:
            self.log("[GIFT] receiver photo lookup failed:", repr(exc))
        return ""

    def process_occupants_for_invite(self, result):
        room = (self.invite_room or result.get("_occupants_room") or
                self.last_joined_room or self.room)
        room = str(room or "").strip()
        # A successful occupants response proves that this room is reachable
        # in the current WebSocket session. Keep it out of the persisted
        # history logic: connected_rooms is intentionally session-only.
        if room:
            self.connected_rooms.add(room)

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

        # Cache the bot's own room role before removing it from the invitation roster.
        for u in users_info:
            if _norm_user(u.get("username")) == _norm_user(BOT_ID):
                bot_role = str(u.get("role") or "").casefold().strip()
                if bot_role:
                    self.bot_room_roles[_norm_room(room)] = bot_role
                break

        pending_role = getattr(self, "_pending_inv_role_check", {}).pop(_norm_room(room), None)
        if pending_role is not None:
            bot_role = self._bot_room_role(room)
            if bot_role not in {"owner", "creator", "room_owner", "room_creator"}:
                self.send_room_text(room, "⚠️ ارفع البوت أونر راعد المحاولة.")
                return

        # Cache the complete room list, including role categories. The disk
        # roster is append/update-only: a transient leave event never erases history.
        if users_info:
            self.room_users[room] = {u["username"]: u.get("role", "none") for u in users_info}
            _remember_roster(room, users_info)

        # A roster refresh requested on room entry is only for persistence.
        # It must never start invitations unless the master explicitly used inv.
        if not self.invite_pending:
            if pending_role is not None:
                usernames = [u["username"] for u in users_info if _norm_user(u.get("username")) != _norm_user(BOT_ID)]
                if not usernames:
                    self.send_room_text(room, "📭 لا يوجد أعضاء لإرسال الدعوات لهم.")
                    return
                self.invite_pending = True
                self.invite_silent_master = False
                self.invite_room = room
                self.invite_sent.clear()
                response_room = str((pending_role or {}).get("room") or room).strip()
                threading.Thread(target=self._finish_invites, args=(room, usernames), name="talkin-invites", daemon=True).start()
            return

        if not users_info:
            self.log("[INV] occupants response received but no usernames decoded")
            try:
                self.send_private_text(BOT_MASTER, "⚠️ وصلت بيانات إعدادات الغرفة لكن لم أستطع استخراج أسماء المستخدمين.")
            except Exception:
                pass
            with self.invite_lock:
                self.invite_pending = False
                self.invite_silent_master = False
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


    def send_room_media(self, room: str, media_url: str, media_type: str, duration: int = 0):
        """Send room media using Query's normal room/url fields.

        Text messages already prove that Query field ``room`` (field 6) is
        the room identifier. Media uses the same field; ``length`` (field 3)
        carries the optional audio duration. Putting the room in ``password``
        made Talkin accept the packet but discard the image/audio payload.
        """
        if media_type == "audio":
            return self.send_query(encode_query(
                "room_message", type_="audio",
                length=str(max(0, int(duration or 0))), room=room, url=media_url
            ))
        return self.send_query(encode_query(
            "room_message", type_=media_type, room=room, url=media_url
        ))

    def _music_download(self,query):
        """Search/download public audio and return an MP3 ready for TalkinChat.

        Primary source: SoundCloud (public audio, independent of YouTube).
        Fallback: YouTube through yt-dlp with optional YOUTUBE_COOKIES.
        Public YouTube/Spotify URLs are first resolved to a title so the
        SoundCloud route can still be used when YouTube extraction is blocked.
        """
        if yt_dlp is None:
            raise RuntimeError("yt-dlp غير مثبت")

        outdir=BASE_DIR/"generated_music"
        outdir.mkdir(parents=True,exist_ok=True)
        stamp=uuid.uuid4().hex
        out_mp3=outdir/(stamp+".mp3")
        errors=[]

        def resolve_public_title(value):
            """Get public page title without downloading media."""
            try:
                u=str(value or "").strip()
                if not re.match(r"^https?://",u,re.I):
                    return ""
                if "youtube.com" in u.lower() or "youtu.be" in u.lower():
                    r=requests.get("https://www.youtube.com/oembed",params={"url":u,"format":"json"},
                                   headers={"User-Agent":"Mozilla/5.0"},timeout=15)
                    if r.ok:
                        data=r.json()
                        return str(data.get("title") or "").strip()
                if "open.spotify.com" in u.lower():
                    r=requests.get(u,headers={"User-Agent":"Mozilla/5.0"},timeout=15)
                    if r.ok:
                        m=re.search(r'<meta[^>]+property=[\"\']og:title[\"\'][^>]+content=[\"\']([^\"\']+)',r.text,re.I)
                        if not m:
                            m=re.search(r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+property=[\"\']og:title[\"\']',r.text,re.I)
                        if m:
                            title=re.sub(r'\s*\|\s*Spotify\s*$','',m.group(1),flags=re.I).strip()
                            return title
            except Exception as exc:
                errors.append(f"Public metadata: {type(exc).__name__}: {exc}")
            return ""

        def normalize_to_mp3(source, duration=0):
            if duration and int(duration) > MUSIC_MAX_SECONDS:
                raise RuntimeError(f"الأغنية أطول من {MUSIC_MAX_SECONDS} ثانية")
            source=Path(source)
            if source.suffix.lower()==".mp3":
                return source
            ffmpeg_bin=shutil.which("ffmpeg")
            if not ffmpeg_bin:
                raise RuntimeError("FFmpeg غير موجود داخل Railway")
            proc=subprocess.run([
                ffmpeg_bin,"-y","-hide_banner","-loglevel","error",
                "-i",str(source),"-vn","-ac","2","-ar","44100",
                "-codec:a","libmp3lame","-b:a","192k",str(out_mp3)
            ],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=180)
            if proc.returncode!=0 or not out_mp3.is_file() or out_mp3.stat().st_size<=4096:
                detail=" | ".join((proc.stderr or "").strip().splitlines()[-4:])
                raise RuntimeError("فشل تحويل الصوت إلى MP3: "+detail[:500])
            try: source.unlink()
            except Exception: pass
            return out_mp3

        def download_with_ydl(target,label,cookies=False):
            tmpdir=outdir/f".{stamp}_{label}"
            tmpdir.mkdir(parents=True,exist_ok=True)
            template=str(tmpdir/"source.%(ext)s")
            opts={
                "quiet":True,"no_warnings":True,"noplaylist":True,
                "format":"bestaudio/best","outtmpl":template,
                "socket_timeout":45,"retries":5,"fragment_retries":5,
                "extractor_retries":3,"file_access_retries":3,
                "cachedir":False,"overwrites":True,
                "concurrent_fragment_downloads":1,
                "http_headers":{"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"},
                "check_formats":False,
                "js_runtimes":{"node":{}},
                "remote_components":{"ejs":"github"},
            }
            if cookies and YOUTUBE_COOKIE_FILE:
                opts["cookiefile"]=YOUTUBE_COOKIE_FILE
            if label.startswith("youtube_"):
                client=label.split("_",1)[1]
                if client != "native_default":
                    opts["extractor_args"]={"youtube":{"player_client":[client]}}
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info=ydl.extract_info(target,download=True)
                    if info and info.get("entries"):
                        info=next((x for x in info["entries"] if x),None)
                    if not info:
                        raise RuntimeError("لم يتم العثور على الأغنية")
                candidates=[x for x in tmpdir.iterdir() if x.is_file() and x.suffix.lower() not in (".part",".ytdl",".temp") and x.stat().st_size>4096]
                if not candidates:
                    raise RuntimeError("تم العثور على الأغنية لكن لم يكتمل الملف الصوتي")
                source=max(candidates,key=lambda x:x.stat().st_mtime)
                duration=int(info.get("duration") or 0)
                mp3=normalize_to_mp3(source,duration)
                return {
                    "id":str(info.get("id") or ""),
                    "title":str(info.get("title") or query),
                    "uploader":str(info.get("uploader") or info.get("channel") or ""),
                    "duration":duration,
                },mp3
            except Exception as exc:
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
                shutil.rmtree(tmpdir,ignore_errors=True)
                return None

        # Resolve URL to a searchable title when possible. This lets a
        # blocked YouTube/Spotify URL still use SoundCloud as the source.
        search_query=str(query or "").strip()
        if re.match(r"^https?://",search_query,re.I):
            title=resolve_public_title(search_query)
            if title:
                search_query=title

        # -------- SoundCloud primary source --------
        sc_targets=[]
        if re.match(r"^https?://",query,re.I) and "soundcloud.com" in query.lower():
            sc_targets=[query]
        elif search_query:
            sc_targets=["scsearch1:"+search_query]

        for target in sc_targets:
            result=download_with_ydl(target,"soundcloud",cookies=False)
            if result:
                info,mp3=result
                for child in outdir.glob(f".{stamp}_*"):
                    if child.is_dir(): shutil.rmtree(child,ignore_errors=True)
                return info,mp3

        # -------- YouTube fallback --------
        youtube_target=query if re.match(r"^https?://",query,re.I) else "ytsearch1:"+query
        for client in ("web_embedded","default","native_default"):
            result=download_with_ydl(youtube_target,f"youtube_{client}",cookies=True)
            if result:
                info,mp3=result
                for child in outdir.glob(f".{stamp}_*"):
                    if child.is_dir(): shutil.rmtree(child,ignore_errors=True)
                return info,mp3

        detail=" | ".join(errors[-10:])
        raise RuntimeError("تعذر تنزيل ملف صوت من SoundCloud أو YouTube."+(f" تفاصيل: {detail[:1200]}" if detail else ""))

    def handle_music_command(self,room,text,requester,private_to=""):
        raw=text.strip()
        if not raw.lower().startswith(".sa "): return False
        query=raw[4:].strip()
        if not query: self.send_room_text(room,"❌ اكتب: .sa اسم الأغنية"); return True
        now=time.time(); last=self.music_last.get(requester,0)
        if now-last<MUSIC_COOLDOWN: self.send_room_text(room,f"⏳ انتظر {int(MUSIC_COOLDOWN-(now-last))+1} ثانية."); return True
        self.music_last[requester]=now
        def worker():
            try:
                public_base = _public_base_url()
                if not public_base: raise RuntimeError("لا يوجد رابط عام للصوت؛ أنشئ Railway Public Domain أو ضع PUBLIC_BASE_URL")
                info,path=self._music_download(query)
                title=str(info.get("title") or query)
                artist=str(info.get("uploader") or info.get("channel") or "YouTube")
                duration=int(info.get("duration") or 0)
                url=public_base+"/media/"+path.name
                self.music_current[_norm_user(requester)] = {
                    "requester": requester, "title": title, "artist": artist,
                    "url": url, "duration": duration, "created_at": time.time(),
                }
                # Music posts use the user's messages.json template.  The
                # reaction code is intentionally limited to 4 characters.
                code=uuid.uuid4().hex[:4]
                caption=_message_template(
                    "music", "broadcast",
                    "🎵 {title}\n🎤 {requester_name}\n🎶 {title}\n📡 المصدر: {source_label}\n🏠 الغرفة الأصلية: {room}\n━━━━━━━━━━━━━\n👍 lk@{code}\n❤️ lv@{code}\n👎 dl@{code}\n💬 cm@{code} msg\n🚨 report@{code} msg",
                    requester_name=requester, title=title, artist=artist,
                    source_label=artist or "Music", room=room, code=code,
                    url=url, duration=duration
                )
                # Music is broadcast to every room currently joined by the bot.
                # Do not send a duplicate private song message to the requester.
                self.reaction_targets[code] = {"publisher": requester, "kind": "music", "title": title, "description": title, "created_at": time.time()}
                target_rooms=self._active_rooms()
                for target_room in target_rooms:
                    self.send_room_text(target_room,caption)
                    self.send_room_media(target_room,url,"audio",duration)
            except Exception as e:
                self.report_master_error("تشغيل الأغنية", e, room)
                self.send_room_text(room, "❌ تعذر تشغيل الأغنية. تم إرسال الخطأ الحقيقي للماستر.")
        threading.Thread(target=worker,name="music-request",daemon=True).start(); self.send_room_text(room,"⏳ جاري البحث عن الأغنية وتحضير الصوت..."); return True

    def share_last_music(self, sender: str, target: str, room: str = ""):
        """Share the sender's latest successfully prepared song privately."""
        target = str(target or "").strip().lstrip("@")
        info = self.music_current.get(_norm_user(sender), {})
        if not target or not info.get("url"):
            self.send_room_text(room, "⚠️ لا توجد أغنية شغّلها المستخدم بعد لمشاركتها.") if room else self.send_private_text(sender, "⚠️ لا توجد أغنية شغّلتها بعد لمشاركتها.")
            return True
        title = str(info.get("title") or "أغنية")
        self.send_private_text(target, f"🎵 مشاركة أغنية من @{sender}\n🎶 {title}")
        self.send_private_media(target, str(info["url"]), "audio", int(info.get("duration") or 0))
        if room:
            self.send_room_text(room, f"✅ تمت مشاركة أغنية {title} مع @{target} في الخاص.")
        else:
            self.send_private_text(sender, f"✅ تمت مشاركة أغنية {title} مع @{target} في الخاص.")
        return True

    def send_gift_native(self, room: str, gift_id: str, target_username: str):
        """Legacy/native packet kept for diagnostics only. Gift command now sends the real asset image."""
        kwargs = {"room": room}
        kwargs[GIFT_TARGET_FIELD] = target_username
        kwargs[GIFT_ID_FIELD] = gift_id
        return self.send_query(encode_query("gifts", type_=GIFT_PROTOCOL, **kwargs))

    def gift_help(self, room):
        lines = ["🎁 الهدايا المتاحة:"]
        for k, (emoji, name) in GIFT_CATALOG.items():
            lines.append(f"{k} {emoji} {name}")
        lines.append("📌 الإرسال: sa@رقم_الهدية@اسم_المستخدم")
        self.send_room_text(room, "\n".join(lines))

    def _verify_public_media_url(self, url: str, media_kind: str = "image"):
        try:
            r=requests.get(url,headers={"Range":"bytes=0-4095","User-Agent":"TalkinBot/22"},timeout=15,stream=True)
            ctype=(r.headers.get("Content-Type") or "").lower()
            if r.status_code not in (200,206):
                raise RuntimeError(f"الرابط العام أعاد HTTP {r.status_code}")
            if media_kind=="image" and not ctype.startswith("image/"):
                raise RuntimeError(f"نوع الصورة غير صحيح: {ctype or 'unknown'}")
            if media_kind=="audio" and not (ctype.startswith("audio/") or "octet-stream" in ctype):
                raise RuntimeError(f"نوع الصوت غير صحيح: {ctype or 'unknown'}")
            return True
        except Exception as exc:
            self.log("[MEDIA] public URL check failed:",repr(exc))
            raise RuntimeError(f"الرابط العام للوسائط غير قابل للوصول: {exc}") from exc

    def _set_profile_status(self, status: str):
        """Update the bot profile status and restore it after a timed gift status.

        The primary bot's base status is configured with BOT_BASE_STATUS because
        Talkin does not expose the current profile text in the room bootstrap.
        A new gift cancels the previous timer and replaces its temporary status.
        PROFILE_STATUS_ACTION allows deployments using a different Talkin build
        to select the matching profile-update action without changing code.
        """
        status = str(status or "").strip()
        if len(status) > PROFILE_STATUS_MAX_CHARS:
            # Keep the important formatted lines when a server has a short
            # profile-status limit; never send a partial/unclosed HTML block.
            compact_base = (
                f'<b><font color="#b73206">بوت حمايه والعاب واغاني</font><br>'
                f'<font color="#FFE87C">لمعرفه الالعاب والاوامر ارسل مساعده</font><br>'
                f'<font color="#af0365">لدخول الغرف ارسل دخول اسم الغرفه</font><br>'
                f'<font color="#66D9FF">الماستر: {MASTER_DISPLAY_NAME}</font></b>'
            )
            status = status.split("<br>", 3)[0] + "<br>" + compact_base
            if len(status) > PROFILE_STATUS_MAX_CHARS:
                status = re.sub(r"\s+", " ", status)[:PROFILE_STATUS_MAX_CHARS]
        try:
            sent = False
            for action in PROFILE_STATUS_ACTIONS:
                try:
                    self.send_query(encode_query(
                        action,
                        type_="status",
                        body=status,
                        value=status,
                    ))
                    self.log("[PROFILE] status update sent via", action)
                    sent = True
                except Exception as exc:
                    self.log("[PROFILE] action failed", action, repr(exc))
            if not sent:
                self.log("[PROFILE] all status update actions failed")
            return sent
        except Exception as exc:
            self.log("[PROFILE] status update failed:", repr(exc))
            return False

    def _set_temporary_gift_status(self, sender: str, receiver: str, gift_name: str):
        sender = str(sender or "").strip().lstrip("@")
        receiver = str(receiver or "").strip().lstrip("@")
        gift_name = str(gift_name or "هدية").strip()
        # Keep sender and receiver on separate colored lines and append the
        # configured base status below them instead of replacing it.
        temporary = (
            f'<font color="#66D9FF">🎁 المرسل: {sender}</font>'
            f'<br><font color="#FF9ED8">🎁 المستقبل: {receiver}</font>'
            f'<br><font color="#FFE29A">{gift_name}</font>'
        )
        with self._profile_status_lock:
            self._profile_status_token += 1
            token = self._profile_status_token
            timer = self._profile_status_timer
            if timer is not None:
                timer.cancel()
            base_status = str(self._profile_current_status or self._profile_base_status or "").strip()
            self._profile_base_status = base_status
            # Send one profile-status update only: the gift lines are above
            # the previous/base status in the same value, not a new status.
            self._set_profile_status(
                temporary + (f"<br>{base_status}" if base_status else "")
            )

            def restore():
                with self._profile_status_lock:
                    if token != self._profile_status_token:
                        return
                    self._profile_status_timer = None
                    self._set_profile_status(self._profile_base_status)
                    self._profile_current_status = self._profile_base_status

            self._profile_status_timer = threading.Timer(GIFT_STATUS_SECONDS, restore)
            self._profile_status_timer.daemon = True
            self._profile_status_timer.start()

    def handle_gift_command(self, room: str, text: str, sender_name: str = "", private_to: str = ""):
        raw=text.strip(); m=re.match(r"^sa@([^@]+)@(.+)$",raw,re.I)
        if not m: return False
        gift_id=m.group(1).strip(); target=m.group(2).strip(); item=GIFT_CATALOG.get(gift_id)
        if not item or not target:
            self.reply_text(room,"❌ الصيغة: sa@رقم_الهدية@اسم_المستخدم",private_to); return True
        try:
            sender_name = str(sender_name or BOT_ID)
            if not _is_verified_user(sender_name):
                self.reply_text(room, f"🔒 @{sender_name} يحتاج توثيق VIP لإرسال الهدايا.\n{_verification_notice()}", private_to)
                return True
            if not _is_verified_user(target):
                self.reply_text(
                    room,
                    f"🔒 المستلم @{target} غير موثق.\n📩 اطلب توثيق VIP للمستلم أولاً ثم أعد إرسال الهدية.",
                    private_to
                )
                return True
            # Giant Chat point costs; owner/masters have unlimited points.
            cost=int(GIFT_COSTS.get(str(gift_id),0)); charged=False
            if not _is_master_name(sender_name):
                balance=_get_points(sender_name)
                if balance < cost:
                    self.reply_text(room,f"❌ رصيدك غير كافٍ. الهدية تحتاج {_fmt_points(cost)} نقطة، ورصيدك {_fmt_points(balance)}.",private_to); return True
                _add_points(sender_name,-cost); charged=True
            # Render and send the real gift card image, then send the gift text.
            # The image is hosted by the bot media server under /gifts/.
            public_base = _public_base_url()
            if not public_base:
                if charged:
                    _add_points(sender_name, cost)
                raise RuntimeError("لا يوجد رابط عام لصور الهدايا؛ أنشئ Railway Public Domain أو ضع PUBLIC_BASE_URL")
            sender_key = sender_name.casefold().lstrip("@")
            receiver_key = target.casefold().lstrip("@")
            # Use each account's own cached/profile image beside its own name.
            sender_photo_url = self.user_photos.get(sender_key, "") or self._lookup_profile_photo(sender_name)
            receiver_photo_url = self.user_photos.get(receiver_key, "") or self._lookup_profile_photo(target)
            gift_path = render_gift_card(gift_id, sender_name, target, sender_photo_url, receiver_photo_url)
            gift_url = public_base + "/gifts/" + gift_path.name
            self._verify_public_media_url(gift_url, "image")
            if not gift_path.is_file() or gift_path.stat().st_size < 64:
                raise RuntimeError(f"ملف صورة الهدية غير صالح: {gift_path}")
            # Put the gift notice above the configured base status in one
            # bounded profile-status value, then restore the base status later.
            self._set_temporary_gift_status(
                sender_name,
                target,
                GIFT_CATALOG.get(str(gift_id), ("🎁", "هدية"))[1],
            )
            if private_to:
                self.send_private_media(private_to, gift_url, "image")
                self.send_private_text(private_to, f"🎁 {item[0]} {item[1]} | 📤 {sender_name} ➜ 📥 {target} | 💰 {cost} نقطة")
            else:
                gift_text = f"🎁 {item[0]} {item[1]} | 📤 {sender_name} ➜ 📥 {target} | 💰 {cost} نقطة"
                self._broadcast_gift_to_all_rooms(gift_url, gift_text, room)
        except Exception as e:
            self.report_master_error("إرسال صورة الهدية", e, room)
            self.reply_text(room, "❌ تعذر إرسال صورة الهدية. تم إرسال الخطأ الحقيقي للماستر.", private_to)
        return True

    def _broadcast_gift_to_all_rooms(self, gift_url: str, gift_text: str, exclude_room: str = ""):
        """Send the gift image and its message to every room the bot currently knows."""
        rooms = set()
        for source in (
            getattr(self, "known_rooms", set()) or set(),
            getattr(self, "rooms", {}) or {},
        ):
            try:
                rooms.update(str(r).strip() for r in source if str(r).strip())
            except Exception:
                pass
        current = str(getattr(self, "room", "") or "").strip()
        if current:
            rooms.add(current)

        # Send sequentially to avoid a burst of WebSocket packets.
        sent = 0
        for r in sorted(rooms):
            try:
                self.send_room_media(r, gift_url, "image")
                self.send_room_text(r, gift_text)
                sent += 1
                time.sleep(0.08)
            except Exception as exc:
                self.log("[GIFT] broadcast failed:", r, repr(exc))
        return sent

    # ----------------------------- Mini Games -----------------------------
    def _game_award(self, username, amount):
        if not username or _is_primary_master(username):
            return _get_points(username)
        return _add_points(username, int(amount))

    def _game_ready(self, username, room, cooldown=30.0, game_name=""):
        # فاصل 30 ثانية لكل لعبة على حدة لكل لاعب.
        # لعب لعبة أخرى لا يفعّل فاصل هذه اللعبة، والفاصل موحّد عبر الغرف.
        game_key=_norm_user(game_name) or "general"
        key=(game_key, _norm_user(username))
        now=time.time()
        with self.game_lock:
            last=self.game_cooldown.get(key,0.0)
            if now-last < cooldown:
                return False, int(cooldown-(now-last))+1
            self.game_cooldown[key]=now
        return True,0

    def _game_cooldown_notice(self, room, username, cooldown=30.0, game_name=""):
        ok, left = self._game_ready(username, room, cooldown, game_name)
        if not ok:
            self.send_room_text(room, f"⏳ @{username} انتظر {left} ثانية قبل لعب لعبة أخرى.")
        return ok

    def _send_game_result(self, room, text, game_key):
        """Send a solo-game result only to the room where that game was played."""
        self.send_room_text(room, text)
        filename = GAME_IMAGE_FILES.get(game_key)
        base = _public_base_url()
        image = ASSETS_DIR / filename if filename else None
        if base and image and image.is_file():
            try:
                self.send_room_media(room, f"{base}/assets/{filename}", "image")
            except Exception as exc:
                self.log("[GAME] result image failed:", repr(exc))

    def game_help(self, room):
        self.send_room_text(room, "🎮✨ ألعاب البوت\n━━━━━━━━━━━━\n"
            "🎲 رهان@المبلغ — تحدي لاعب ضد لاعب، والفائز عشوائي.\n"
            "⚔️ مضاربة@المبلغ — مواجهة عشوائية عادلة، لا أفضلية للأول أو الثاني.\n"
            "🍀 حظ — لعبة عشوائية مع البوت.\n"
            "🎯 حظ@المبلغ — حظ عشوائي بمبلغ ضد البوت.\n"
            "🎯 حظي@المبلغ — تحدي حظ لاعب ضد لاعب.\n"
            "📊 استثمار@المبلغ — استثمار لاعب ضد لاعب مثل الرهان.\n"
            "🤖 استثمار — استثمار مجاني مع البوت بدون مبلغ.\n"
            "🎰 مليون — فرصة عشوائية للفوز بمليون نقطة.\n"
            "🌱 زرع — حتى 5 محاصيل نشطة لكل مستخدم، وكل نوع مرة واحدة فقط.\n"
            "🆕 صيد | سرعة | كنز | مصارعة | بحث — ألعاب عالمية، الجائزة 500 نقطة.\n"
            "🕵️ اسرق — اختر عضوًا عشوائيًا وحاول سرقة 500 نقطة منه.\n"
            "🏆 توب رهان | توب مضاربة | توب حظي | توب استثمار")

    def _game_balance_ok(self, username, amount):
        return _is_primary_master(username) or _get_points(username) >= int(amount)

    def _reserved_stake(self, username, exclude_key=None):
        key = _norm_user(username)
        total = 0
        with self.game_lock:
            for k, waiting in self.wager_waiting.items():
                if exclude_key is not None and k == exclude_key:
                    continue
                if _norm_user(waiting.get("user")) == key:
                    total += int(waiting.get("stake", 0) or 0)
        return total

    def _cleanup_expired_wagers(self):
        timeout = max(30, int(os.getenv("WAGER_TIMEOUT_SECONDS", "180")))
        now = time.time()
        expired = []
        with self.game_lock:
            for key, waiting in list(self.wager_waiting.items()):
                if now - float(waiting.get("created", 0) or 0) >= timeout:
                    expired.append((key, waiting))
                    self.wager_waiting.pop(key, None)
        for _, waiting in expired:
            self.log("[GAME] expired wager", waiting.get("game"), waiting.get("user"))

    def _wager_result(self, first, second, game_name):
        """Resolve a global PvP wager and publish the result only to both origin rooms."""
        winner, loser = (first, second) if secrets.randbelow(2) == 0 else (second, first)
        winner_stake = int(winner.get("stake", 0) or 0)
        loser_stake = int(loser.get("stake", 0) or 0)

        # Each player risks the amount they entered. The winner receives the
        # opponent's stake; the winner's own stake is returned implicitly.
        if not _is_master_name(loser.get("user")):
            _add_points(loser.get("user"), -loser_stake)
        if not _is_master_name(winner.get("user")):
            _add_points(winner.get("user"), loser_stake)

        game_key = {
            "رهان":"bet", "مراهنة":"bet", "مضاربة":"duel", "مضاربه":"duel",
            "استثمار":"investment", "حظي":"luck"
        }.get(game_name, game_name.casefold())
        _record_game(loser.get("user"), game_key, -loser_stake, loser_stake)
        _record_game(winner.get("user"), game_key, loser_stake, loser_stake)

        text = _reply_template(
            "wager_result",
            DEFAULT_REPLY_MESSAGES["wager_result"],
            game=game_name,
            p1=first["user"], p2=second["user"],
            winner=winner["user"], loser=loser["user"],
            amount=_fmt_points(loser_stake),
        )

        # IMPORTANT: the queue is global across rooms, but the result is local
        # to exactly the two rooms where the two players entered the game.
        result_rooms = []
        seen_rooms = set()
        for target in (first.get("room"), second.get("room")):
            target = str(target or "").strip()
            key = target.casefold()
            if target and key not in seen_rooms:
                seen_rooms.add(key)
                result_rooms.append(target)

        for result_room in result_rooms:
            self.send_room_text(result_room, text)

        filename = GAME_IMAGE_FILES.get(game_key)
        base = _public_base_url()
        image = ASSETS_DIR / filename if filename else None
        if filename and base and image and image.is_file():
            for result_room in result_rooms:
                try:
                    self.send_room_media(result_room, f"{base}/assets/{filename}", "image")
                except Exception as exc:
                    self.log("[GAME] wager result image failed:", result_room, repr(exc))

    def _queue_wager(self, room, sender, game_name, amount):
        try:
            amount = int(amount)
        except Exception:
            return True
        if amount <= 0:
            self.send_room_text(room, _reply_template("game_invalid_amount", DEFAULT_REPLY_MESSAGES["game_invalid_amount"]))
            return True
        # The 30-second interval belongs to this game only; another game can be played immediately.
        if not self._game_cooldown_notice(room, sender, 30.0, game_name):
            return True

        self._cleanup_expired_wagers()
        # GLOBAL queue: the same game challenge is shared by every room.
        # Same-room play is allowed; room is intentionally NOT part of the key.
        key = game_name.casefold()
        waiting = None
        error = None
        with self.game_lock:
            waiting = self.wager_waiting.get(key)
            if waiting and _norm_user(waiting["user"]) == _norm_user(sender):
                return True

            # A player cannot spend points that are already committed to another
            # open global challenge. The current challenge itself is excluded.
            reserved = sum(
                int(w.get("stake", 0) or 0) for k, w in self.wager_waiting.items()
                if k != key and _norm_user(w.get("user")) == _norm_user(sender)
            )
            if not _is_primary_master(sender):
                balance = _get_points(sender)
                if balance < amount + reserved:
                    error = _reply_template(
                        "game_insufficient", DEFAULT_REPLY_MESSAGES["game_insufficient"],
                        balance=_fmt_points(balance)
                    )

            if error is None and waiting:
                # A second player may enter ANY amount, from the same room or another room.
                # Their room and stake are both preserved for the final result.
                self.wager_waiting.pop(key, None)
            elif error is None:
                self.wager_waiting[key] = {
                    "user": sender,
                    "room": room,
                    "stake": amount,
                    "game": game_name,
                    "created": time.time(),
                }

        if error:
            self.send_room_text(room, error)
            return True

        if waiting:
            second = {
                "user": sender,
                "room": room,
                "stake": amount,
                "game": game_name,
            }
            self._wager_result(waiting, second, game_name)

            # _game_ready already recorded the 30-second cooldown per game/user.
            # It is independent of room, so changing rooms or using another game
            # does not create a false cooldown.
            return True

        game_labels = {
            "رهان": ("رهان", "راهن", "رهان"),
            "مراهنة": ("رهان", "راهن", "رهان"),
            "مضاربة": ("مضاربة", "ضارب", "مضاربة"),
            "مضاربه": ("مضاربة", "ضارب", "مضاربة"),
            "استثمار": ("استثمار", "استثمر", "استثمار"),
            "حظي": ("حظي", "راهن", "حظي"),
        }
        game_label, verb, command = game_labels.get(game_name, (game_name, "لاعب", game_name))
        opening = _reply_template(
            "wager_open", DEFAULT_REPLY_MESSAGES["wager_open"],
            game_label=game_label, verb=verb, command=command,
            username=sender, amount=_fmt_points(amount)
        )
        # GLOBAL challenge announcement: every tracked bot room sees the same
        # open challenge, regardless of where the first player started it.
        self.broadcast_all_rooms(opening)
        return True

    def _fixed_game_result(self, first, second, game_name, prize=500):
        """Resolve a global fixed-prize game. Winner +prize, loser -prize.
        The challenge is global, while the final text/image is sent only to the
        two rooms where the two players entered.
        """
        prize = int(prize)
        winner, loser = (first, second) if secrets.randbelow(2) == 0 else (second, first)

        # Re-check balances at settlement so a player cannot join with 500,
        # spend it elsewhere, and then fall below the fixed loss amount.
        for player in (first, second):
            username = player.get("user")
            if not _is_primary_master(username) and _get_points(username) < prize:
                rooms=[]
                for target in (first.get("room"), second.get("room")):
                    target=str(target or "").strip()
                    if target and target.casefold() not in {r.casefold() for r in rooms}:
                        rooms.append(target)
                msg=f"⚠️ تم إلغاء جولة {game_name}. اللاعب @{username} لا يملك {prize} نقطة كافية للمخاطرة."
                for r in rooms:
                    self.send_room_text(r,msg)
                return

        if not _is_primary_master(loser.get("user")):
            _add_points(loser.get("user"), -prize)
        if not _is_primary_master(winner.get("user")):
            _add_points(winner.get("user"), prize)

        game_key=game_name
        _record_game(loser.get("user"), game_key, -prize, prize)
        _record_game(winner.get("user"), game_key, prize, prize)

        text=(
            f"🏆 انتهت لعبة {game_name}\n"
            f"━━━━━━━━━━━━\n"
            f"👤 اللاعب الأول: @{first['user']}\n"
            f"👤 اللاعب الثاني: @{second['user']}\n\n"
            f"👑 الفائز: @{winner['user']}\n"
            f"🎁 المكافأة: +{_fmt_points(prize)} نقطة\n"
            f"📉 الخاسر: @{loser['user']} (-{_fmt_points(prize)} نقطة)\n"
            f"━━━━━━━━━━━━"
        )

        result_rooms=[]
        seen=set()
        for target in (first.get("room"), second.get("room")):
            target=str(target or "").strip()
            key=target.casefold()
            if target and key not in seen:
                seen.add(key); result_rooms.append(target)
        for result_room in result_rooms:
            self.send_room_text(result_room,text)

        filename=GAME_IMAGE_FILES.get(game_name)
        base=_public_base_url()
        image=ASSETS_DIR / filename if filename else None
        if base and image and image.is_file():
            for result_room in result_rooms:
                try:
                    self.send_room_media(result_room,f"{base}/assets/{filename}","image")
                except Exception as exc:
                    self.log("[GAME] fixed result image failed:",result_room,repr(exc))

    def _queue_fixed_game(self, room, sender, game_name, prize=500):
        """Global two-player queue; both players may enter from the same room or different rooms."""
        prize=int(prize)
        if not self._game_cooldown_notice(room,sender,30.0,game_name):
            return True
        if not _is_primary_master(sender) and _get_points(sender) < prize:
            self.send_room_text(room,f"❌ تحتاج {prize} نقطة للمشاركة في {game_name}. رصيدك: {_fmt_points(_get_points(sender))}")
            return True

        with self.game_lock:
            waiting=self.fixed_game_waiting.get(game_name)
            if waiting and _norm_user(waiting.get("user")) == _norm_user(sender):
                return True
            if waiting:
                self.fixed_game_waiting.pop(game_name,None)

        if waiting:
            second={"user":sender,"room":room}
            self._fixed_game_result(waiting,second,game_name,prize)
            # Cooldown was already recorded by _game_ready using only game + user.
            # Same-room participation remains allowed.
            return True

        challenge=(
            f"🎮🔥 لعبة {game_name} جديدة!\n"
            f"━━━━━━━━━━━━\n"
            f"👤 اللاعب: @{sender}\n"
            f"🎁 جائزة الجولة: {_fmt_points(prize)} نقطة\n"
            f"🌍 الجولة عالمية بين جميع غرف البوت\n\n"
            f"🤝 للمشاركة اكتب: {game_name}"
        )
        with self.game_lock:
            # Re-check in case another event created the queue while we prepared.
            if game_name not in self.fixed_game_waiting:
                self.fixed_game_waiting[game_name]={"user":sender,"room":room,"created":time.time()}
            else:
                return True
        self.broadcast_all_rooms(challenge)
        return True

    def _fruit_match(self, room, sender, emoji):
        if not self._game_cooldown_notice(room, sender, 30.0, "فيس"):
            return True
        fruits=("🍓","🍇","🍉","🍌","🍋","🍊","🍐","🍎","🍏","🥑","🥦","🍑","🥭","🍍","🥥","🥝","🍅","🍆","🧄","🥕","🌽","🌶️")
        if emoji not in fruits:
            self.send_room_text(room, "❌ اختر فاكهة من القائمة: " + " ".join(fruits)); return True
        bot_fruit=random.choice(fruits)
        if emoji == bot_fruit:
            self._send_game_result(room, f"🍉 فيس @{sender}\n✅ تمت المطابقة! البوت أرسل {bot_fruit}\n🏆 فزت بـ 20 نقطة.", "")
            self._game_award(sender,20)
            _record_game(sender, "fruit", 20, 0)
        else:
            self.send_room_text(room, f"🍉 فيس @{sender}\n🤖 البوت أرسل {bot_fruit}\n❌ لم تتم المطابقة، حظاً موفقاً.")
        return True

    def _save_crop_plots(self):
        try:
            _save_local_json(CROP_PLOTS_FILE, self.crop_plots)
        except Exception as exc:
            self.log("[CROP] save failed:", repr(exc))

    def _crop_worker(self):
        while not self.stop_event.is_set():
            now=time.time()
            ready=[]
            with self.game_lock:
                for key, plot in list(self.crop_plots.items()):
                    try:
                        parts = key.split("|", 2)
                        username, crop = parts[0], parts[1]
                        finish=float(plot.get("finish", 0))
                        minutes=int(plot.get("minutes", 0))
                        reward=int(plot.get("reward", minutes*20))
                    except Exception:
                        continue
                    if now >= finish:
                        ready.append((key, username, crop, minutes, reward))
                for key, *_ in ready:
                    self.crop_plots.pop(key, None)
            if ready:
                self._save_crop_plots()
                for key, username, crop, minutes, reward in ready:
                    balance=self._game_award(username, reward)
                    _record_game(username, "farm", reward, 0)
                    self.send_private_text(
                        username,
                        f"🌾✨ حصادك جاهز!\n━━━━━━━━━━━━\n"
                        f"🌱 المحصول: {crop}\n"
                        f"⏱️ مدة الزراعة: {minutes} دقيقة\n"
                        f"🎁 المكافأة: +{_fmt_points(reward)} نقطة\n"
                        f"💰 رصيدك الآن: {_fmt_points(balance)}\n"
                        f"🌟 زرع جديد عندما تريد!"
                    )
            self.stop_event.wait(2.0)

    def _crop_command(self, room, sender, raw):
        crops={
            "🍎":(5,100), "🍐":(10,200), "🍊":(15,300), "🍋":(20,400),
            "🍇":(25,500), "🍉":(30,600), "🍓":(35,700), "🥕":(40,800),
            "🌽":(45,900), "🥭":(50,1000)
        }
        if raw.casefold()=="زرع":
            self.send_room_text(
                room,
                "🌱 المحاصيل ومدة الانتظار:\n"
                "🍎 5 دقيقة=100 | 🍐 10 دقيقة=200 | 🍊 15 دقيقة=300 | "
                "🍋 20 دقيقة=400 | 🍇 25 دقيقة=500 | 🍉 30 دقيقة=600 | "
                "🍓 35 دقيقة=700 | 🥕 40 دقيقة=800 | 🌽 45 دقيقة=900 | 🥭 50 دقيقة=1000\n"
                "━━━━━━━━━━━━\nاستخدم: زرع@🍎\n"
                "💡 بعد انتهاء الوقت تصلك النتيجة تلقائياً في الخاص."
            )
            return True
        m=re.fullmatch(r"زرع[@ ](.+)", raw, re.I)
        if not m: return False
        crop=m.group(1).strip()
        if crop not in crops:
            self.send_room_text(room, "❌ اختر محصولاً من قائمة زرع.")
            return True
        user_key=_norm_user(sender)
        with self.game_lock:
            # يسمح لكل مستخدم بحد أقصى 5 محاصيل نشطة في الوقت نفسه،
            # وكل نوع محصول مرة واحدة فقط؛ تكرار نفس النوع يكون صامتاً.
            active_user = []
            active_crops = set()
            for key, plot in self.crop_plots.items():
                if key.startswith(user_key + "|"):
                    active_user.append((key, plot))
                    active_crops.add(str(plot.get("crop") or ""))

            if crop in active_crops:
                self.send_room_text(
                    room,
                    f"🌱 ازرع محصولاً آخر.\n"
                    f"📖 الطريقة: اكتب زرع ثم @ ثم رمز المحصول.\n"
                    f"مثال: زرع@🍐\n"
                    f"💡 لا يمكن زراعة نفس النوع مرتين في نفس الوقت."
                )
                return True

            if len(active_user) >= 5:
                self.send_room_text(room, "⏳ لديك 5 محاصيل قيد الزراعة حالياً. احصد أحدها أولاً ثم ازرع محصولاً جديداً.")
                return True

        if not self._game_cooldown_notice(room, sender, 30.0, "زرع"):
            return True

        with self.game_lock:
            # نعيد الفحص بعد الانتظار لتجنب التكرار إذا وصلت زراعة أخرى بالتزامن.
            active_user = []
            active_crops = set()
            for key, plot in self.crop_plots.items():
                if key.startswith(user_key + "|"):
                    active_user.append((key, plot))
                    active_crops.add(str(plot.get("crop") or ""))
            if crop in active_crops:
                self.send_room_text(
                    room,
                    f"🌱 ازرع محصولاً آخر.\n"
                    f"📖 الطريقة: زرع@رمز_المحصول\n"
                    f"مثال: زرع@🍐\n"
                    f"💡 لا يمكن زراعة نفس النوع مرتين في نفس الوقت."
                )
                return True
            if len(active_user) >= 5:
                self.send_room_text(room, "⏳ لديك 5 محاصيل قيد الزراعة حالياً. احصد أحدها أولاً ثم ازرع محصولاً جديداً.")
                return True

            minutes,reward=crops[crop]
            slot=uuid.uuid4().hex[:8]
            key=f"{user_key}|{crop}|{slot}"
            self.crop_plots[key]={
                "username":str(sender).strip().lstrip("@"),
                "crop":crop, "minutes":minutes, "reward":reward,
                "finish":time.time()+minutes*60, "room":str(room or "")
            }
        self._save_crop_plots()
        self.send_room_text(
            room,
            f"🌱 تم زرع {crop} بنجاح!\n"
            f"⏱️ الانتظار: {minutes} دقيقة\n"
            f"🎁 المكافأة: {reward} نقطة\n"
            f"📩 عند اكتمال الزراعة ستصلك النتيجة تلقائياً في الخاص."
        )
        return True

    def _lottery_game(self, room, sender, amount=0):
        if not self._game_cooldown_notice(room, sender, 30.0, game_name):
            return True
        amount = int(amount or 0)
        if amount < 0:
            self.send_room_text(room, "❌ المبلغ غير صحيح.")
            return True
        with self.game_lock:
            if amount and not _is_primary_master(sender):
                balance_before = _get_points(sender)
                if balance_before < amount:
                    self.send_room_text(room, f"❌ رصيدك غير كافٍ. رصيدك: {_fmt_points(balance_before)}")
                    return True
                # The stake is charged exactly once before the random draw.
                _add_points(sender, -amount)
            # Cryptographically strong random draw; the amount is never used as
            # the random seed and cannot force a matching payout.
            roll = secrets.randbelow(1000) + 1
            if roll <= 60:
                multiplier = 5
            elif roll <= 180:
                multiplier = 3
            elif roll <= 400:
                multiplier = 2
            elif roll <= 650:
                multiplier = 1
            else:
                multiplier = 0
            reward = amount * multiplier if amount else secrets.choice((10, 20, 30, 50, 100))
            if reward:
                balance = self._game_award(sender, reward)
                result = f"🎉 ربحت: +{_fmt_points(reward)} نقطة"
            else:
                balance = _get_points(sender)
                result = "🍀 هذه الجولة لم تكن رابحة."
            delta = reward - amount if amount else reward
            _record_game(sender, "luck_free" if not amount else "luck", delta, amount)
        text = _reply_template(
            "luck_result", DEFAULT_REPLY_MESSAGES["luck_result"],
            username=sender, result=result, amount=_fmt_points(amount),
            delta=("+" if delta >= 0 else "") + _fmt_points(delta),
            balance=_fmt_points(balance)
        )
        self.send_room_text(room, text)
        if reward > 0:
            filename = GAME_IMAGE_FILES.get("luck")
            base = _public_base_url()
            image = ASSETS_DIR / filename if filename else None
            if base and image and image.is_file():
                try:
                    self.send_room_media(room, f"{base}/assets/{filename}", "image")
                except Exception as exc:
                    self.log("[GAME] luck result image failed:", repr(exc))
        return True

    def _investment_bot_game(self, room, sender):
        if not self._game_cooldown_notice(room, sender, 30.0, "استثمار"):
            return True
        """Free investment game against the bot. No @amount and no image."""
        # Pure random outcome; no stake and no dependency on command order.
        roll=secrets.randbelow(1000)+1
        if roll <= 120:
            reward=100
        elif roll <= 320:
            reward=50
        elif roll <= 600:
            reward=30
        elif roll <= 850:
            reward=20
        else:
            reward=10
        balance=self._game_award(sender, reward)
        _record_game(sender, "investment", reward, 0)
        self.send_room_text(
            room,
            f"📊✨ استثمار مع البوت\n━━━━━━━━━━━━\n"
            f"👤 اللاعب: @{sender}\n"
            f"🎁 النتيجة: +{_fmt_points(reward)} نقطة\n"
            f"💰 الرصيد: {_fmt_points(balance)}"
        )
        if reward > 0:
            filename = GAME_IMAGE_FILES.get("investment")
            base = _public_base_url()
            image = ASSETS_DIR / filename if filename else None
            if base and image and image.is_file():
                try:
                    self.send_room_media(room, f"{base}/assets/{filename}", "image")
                except Exception as exc:
                    self.log("[GAME] investment result image failed:", repr(exc))
        return True

    def _handle_lookalike_command(self, room, body, sender):
        """Handle شبيه@username / شبيه username in a background worker."""
        if not room:
            return True
        text = str(body or "").strip()
        m = re.fullmatch(r"(?:شبيه|شبيهك)@(.+)", text, re.I)
        if not m:
            m = re.fullmatch(r"(?:شبيه|شبيهك)\s+(.+)", text, re.I)
        if not m:
            return False
        target = m.group(1).strip().lstrip("@").strip()
        if not target:
            self.send_room_text(room, "❌ الصيغة: شبيه@اسم_المستخدم")
            return True
        # Avoid several expensive web searches by the same user at once.
        busy = getattr(self, "_lookalike_busy", set())
        key = (_norm_user(sender), str(room))
        if key in busy:
            self.send_room_text(room, f"⏳ @{sender} جاري البحث عن شبيه @{target}...")
            return True
        busy.add(key)
        self._lookalike_busy = busy
        self.send_room_text(room, f"🔎 جاري البحث عن شبيه @{target}...")

        def worker():
            try:
                # Searching the username itself usually gives the most relevant
                # public results; Arabic "شبيه" is added to broaden lookalike-style results.
                query = f"{target} شبيه"
                image_url = _search_lookalike_image(query)
                if not image_url:
                    self.send_room_text(room, f"❌ لم أجد صورة مناسبة لـ @{target}.")
                    return
                local = _download_lookalike_image(image_url, target)
                if not local:
                    self.send_room_text(room, f"❌ وجدت نتيجة لكن تعذر تحميل الصورة لـ @{target}.")
                    return
                base = _public_base_url()
                if not base:
                    self.send_room_text(room, "❌ رابط الصور العام غير مضبوط في إعدادات البوت.")
                    return
                public_url = f"{base}/lookalikes/{local.name}"
                # The phrase is intentionally a playful result, not an identity claim.
                self.send_room_text(room, f"👤 شبيه @{target} هو")
                self.send_room_media(room, public_url, "image")
            except Exception as exc:
                self.log("[LOOKALIKE] failed:", repr(exc))
                try:
                    self.send_room_text(room, "❌ تعذر البحث عن صورة الشبيه حالياً.")
                except Exception:
                    pass
            finally:
                try:
                    busy.discard(key)
                except Exception:
                    pass

        threading.Thread(target=worker, name="lookalike-search", daemon=True).start()
        return True

    def _send_steal_image(self, room, game_key):
        filename = GAME_IMAGE_FILES.get(game_key)
        base = _public_base_url()
        image = ASSETS_DIR / filename if filename else None
        if base and image and image.is_file():
            try:
                self.send_room_media(room, f"{base}/assets/{filename}", "image")
            except Exception as exc:
                self.log("[GAME] steal result image failed:", repr(exc))

    def _room_member_usernames_for_steal(self, room, exclude_username=""):
        """Return a complete/randomizable member list from the current room."""
        excluded = {_norm_user(exclude_username), _norm_user(BOT_ID)}
        candidates = []
        seen = set()

        def add_user(value):
            u = str(value or "").strip().lstrip("@").strip()
            key = _norm_user(u)
            if not u or not key or key in excluded or key in seen or _is_master_name(u):
                return
            seen.add(key)
            candidates.append(u)

        # Live cache first.
        live = self.room_users.get(room, {}) if room else {}
        if isinstance(live, dict):
            for username in live.keys():
                add_user(username)

        # Complete persistent roster next, including members who are offline.
        try:
            for username in _persistent_roster_users(room):
                add_user(username)
        except Exception as exc:
            self.log("[GAME] persistent steal roster lookup failed:", repr(exc))

        # Native DB roster as an additional fallback/source.
        if getattr(self, "db", None):
            try:
                for item in self.db.room_users(room) or []:
                    if isinstance(item, dict):
                        add_user(item.get("username"))
                    else:
                        add_user(item)
            except Exception as exc:
                self.log("[GAME] steal room member lookup failed:", repr(exc))
        return candidates

    def _steal_game(self, room, sender, requested_victim=""):
        if not self._game_cooldown_notice(room, sender, 30.0, "اسرق"):
            return True

        members = self._room_member_usernames_for_steal(room, sender)
        self.send_room_text(room, f"🕵️ @{sender} جاري البحث عن الضحية...")
        if not members:
            self.send_room_text(room, "❌ فشلت السرقة: لا يوجد عضو آخر متاح للسرقة حالياً.")
            self._send_steal_image(room, "اسرق_فشل")
            _record_game(sender, "steal", 0, 500)
            return True

        # `اسرق` = choose a victim randomly; `اسرق@username` / `اسرق username` = target that member.
        victim = ""
        if requested_victim:
            wanted = _norm_user(requested_victim)
            for candidate in members:
                if _norm_user(candidate) == wanted:
                    victim = candidate
                    break
            if not victim:
                self.send_room_text(room, f"❌ لم أجد @{requested_victim} ضمن أعضاء الغرفة.")
                return True
        else:
            victim = secrets.choice(members)

        victim_balance = _get_points(victim)
        if victim_balance < 500:
            self.send_room_text(
                room,
                f"🕵️ @{sender} حاول سرقة @{victim}...\n"
                f"❌ فشلت السرقة، المسروق @{victim} مفلس.\n"
                f"💰 رصيده: {_fmt_points(victim_balance)}"
            )
            self._send_steal_image(room, "اسرق_فشل")
            _record_game(sender, "steal", 0, 500)
            return True

        # The result is random each attempt: usually success, sometimes the police catch the thief.
        if secrets.randbelow(100) >= 70:
            self.send_room_text(
                room,
                f"🚨 @{sender} حاول سرقة @{victim}...\n"
                f"🚔 السرقة حرام، تم إبلاغ الشرطة! 😁\n"
                f"❌ لم تتم السرقة."
            )
            self._send_steal_image(room, "اسرق_فشل")
            _record_game(sender, "steal", 0, 500)
            return True

        _add_points(victim, -500)
        thief_balance = _add_points(sender, 500)
        self.send_room_text(
            room,
            f"🕵️💰 تمت السرقة بنجاح!\n"
            f"👤 السارق: @{sender}\n"
            f"🎯 الضحية: @{victim}\n"
            f"💸 المسروق: 500 نقطة\n"
            f"🎁 @{sender} حصل على +500 نقطة.\n"
            f"💰 رصيد السارق: {_fmt_points(thief_balance)}"
        )
        self._send_steal_image(room, "اسرق_نجاح")
        _record_game(sender, "steal", 500, 500)
        _record_game(victim, "steal", -500, 500)
        return True

    def handle_game_command(self, room, text, sender_name):
        raw=str(text or "").strip()
        if not raw or not sender_name: return False
        # All games are available to verified accounts (including VIP).
        # The master remains allowed automatically by _is_verified_user().
        # This check is intentionally inside the game handler so game commands
        # can never become master-only because of an external command gate.
        if not _is_verified_user(sender_name):
            self.send_room_text(room, f"🔒 @{sender_name} حسابك غير موثق لاستخدام الألعاب.\n{_verification_notice()}")
            return True
        low=raw.casefold()
        if low in ("العاب","ألعاب","لعب","games","game"):
            self.game_help(room); return True
        if low.startswith("زرع"):
            return self._crop_command(room, sender_name, raw)
        if low.startswith("فيس"):
            m=re.fullmatch(r"فيس[@ ](.+)", raw, re.I)
            return self._fruit_match(room, sender_name, m.group(1).strip() if m else "")
        # New fixed-prize global games. Each one has a single worldwide queue:
        # first verified player opens it, the next verified player joins, then
        # the winner receives +500 and the loser loses 500.
        fixed_games=("صيد","سرعة","كنز","مصارعة","بحث")
        if low in tuple(x.casefold() for x in fixed_games):
            game_name=next(x for x in fixed_games if x.casefold()==low)
            return self._queue_fixed_game(room,sender_name,game_name,500)
        # PvP games: outcome is decided by strong random selection, never by
        # who entered first or second.
        m=re.fullmatch(r"(مراهنة|رهان|مضاربة|مضاربه|حظي)@([0-9]+)", raw, re.I)
        if m:
            return self._queue_wager(room, sender_name, m.group(1), int(m.group(2)))
        # Investment with a stake is PvP, exactly like the wager games.
        m=re.fullmatch(r"استثمار@([0-9]+)", raw, re.I)
        if m:
            return self._queue_wager(room, sender_name, "استثمار", int(m.group(1)))
        # Plain "استثمار" is a free game against the bot, text only.
        if low == "استثمار":
            return self._investment_bot_game(room, sender_name)
        m=re.fullmatch(r"حظ@([0-9]+)", raw, re.I)
        if m:
            return self._lottery_game(room, sender_name, int(m.group(1)))
        if low in ("مليون","million"):
            if not self._game_cooldown_notice(room, sender_name, 30.0, "مليون"):
                return True
            # Restore the first status message used by the original million game.
            self.send_room_text(room, "🔎 جاري البحث عن مليون...")
            time.sleep(1.0)
            won=(secrets.randbelow(100)==0)
            reward=1000000 if won else 0
            _record_game(sender_name,"million",reward,0)
            if won:
                self._game_award(sender_name,reward)
                self._send_game_result(room,
                    f"🎰✨ مليون\n━━━━━━━━━━━━\n"
                    f"🏆 مبروك @{sender_name}!\n"
                    f"💰 الجائزة: +1m نقطة", "million")
            else:
                self.send_room_text(room, f"🎰🍀 مليون\n━━━━━━━━━━━━\nحظ أوفر @{sender_name} في الجولة القادمة!")
            return True
        if low in ("حظ","الحظ","luck"):
            return self._lottery_game(room, sender_name, 0)
        if low in ("حجر","ورق","مقص"):
            if not self._game_cooldown_notice(room, sender_name, 30.0, "حجر_ورق_مقص"):
                return True
            bot_choice=secrets.choice(("حجر","ورق","مقص"))
            win=(low,bot_choice) in (("حجر","مقص"),("ورق","حجر"),("مقص","ورق"))
            if low==bot_choice: result="🤝 تعادل"; reward=5
            elif win: result="🏆 فزت"; reward=15
            else: result="❌ خسرت"; reward=0
            balance=self._game_award(sender_name,reward)
            _record_game(sender_name,"rps",reward,0)
            self.send_room_text(room, f"✂️ @{sender_name}: {low} | 🤖 البوت: {bot_choice}\n{result}\n🎁 +{reward} نقطة\n💰 {_fmt_points(balance)}")
            return True
        # Steal: random victim with `اسرق`, or a named room member with `اسرق@username` / `اسرق username`.
        m=re.fullmatch(r"اسرق(?:@|\s+@?)([^@\s]+)", raw, re.I)
        if m:
            return self._steal_game(room, sender_name, m.group(1).strip().lstrip("@"))
        if low == "اسرق":
            return self._steal_game(room, sender_name)
        if low in ("سرقة", "رشوة"):
            if not self._game_cooldown_notice(room, sender_name, 30.0, "سرقة" if low == "سرقة" else "رشوة"):
                return True
            label = "🕵️ سرقة" if low == "سرقة" else "💼 رشوة"
            won = secrets.randbelow(2) == 0
            reward = secrets.randbelow(31) + 10 if won else 0
            balance = self._game_award(sender_name, reward)
            _record_game(sender_name, "misc", reward, 0)
            self.send_room_text(room, f"{label} @{sender_name}\n" + (f"🏆 نجحت وربحت {reward} نقطة." if won else "❌ لم تنجح هذه المرة.") + f"\n💰 {_fmt_points(balance)}")
            return True
        return False

    def _send_help_section(self, room=None, private_to=None, page=1, part=1):
        sections = _help_sections_from_messages()
        page_sections = sections.get(int(page), [])
        if not page_sections:
            text = _command_help(page)
            part = 1
        else:
            idx = max(1, min(int(part), len(page_sections))) - 1
            text = page_sections[idx]
            if idx < len(page_sections) - 1:
                text += "\n\n📌 للقائمة التالية اكتب Ns"
            else:
                text += "\n\n✅ انتهت أقسام هذه القائمة."
        if private_to:
            self._send_help_chunks("chat_message", text, to=private_to)
        elif room:
            self._send_help_chunks("room_message", text, room=room)

    def _send_game_help_section(self, room=None, private_to=None, part=1):
        # Backward-compatible wrapper for older callers.
        self._send_help_section(room=room, private_to=private_to, page=3, part=part)

    def _send_help(self, room=None, private_to=None, page=1, game_part=1):
        self._send_help_section(room=room, private_to=private_to, page=page, part=game_part)

    def _handle_management_command(self, room, body, sender, is_private=False):
        # Management commands are accepted only from the master. Keep normal
        # response routing enabled so the master receives the result privately
        # (or in the command room when the command is public by design).
        # Publishing is intentionally also available to verified accounts.
        # Public help: menu and pages must be available to ALL users,
        # whether verified, unverified, or master. Handle them before the
        # master-only management gate below.
        _body_text = str(body or "").strip()
        _body_low = _body_text.casefold()
        if _body_low in ("اوامر", "الاوامر", "help", "مساعدة"):
            menu = _command_menu_for(_is_master_name(sender), is_private=is_private)
            if is_private:
                self.send_private_text(sender, menu)
            elif room:
                self.send_room_text(room, menu)
            return True
        _m_public_help = re.fullmatch(r"help([1-6])", _body_low)
        if _m_public_help:
            _page = int(_m_public_help.group(1))
            if _page == 1 and (not _is_master_name(sender) or not is_private):
                return False
            self._send_help(room=room, private_to=sender if is_private else None, page=_page)
            return True

        is_publish = str(body or "").strip().casefold() == "انشر" or str(body or "").strip().casefold().startswith("انشر@")
        security_command = bool(re.match(r"^(?:تشغيل|إيقاف) الحماية$", str(body or "").strip(), re.I) or re.match(r"^mr@\d+$", str(body or "").strip(), re.I))
        join_command = bool(re.match(r"^دخول@.+$", str(body or "").strip(), re.I))
        verification_manager_command = _is_verification_manager_command(body)
        points_transfer_command = bool(re.fullmatch(r"sb@([^@]+)@(\d+)", str(body or "").strip(), re.I))
        if (not _is_master_name(sender)
                and not (verification_manager_command and _is_mvip_master(sender))
                and not (points_transfer_command and _is_verified_user(sender))
                and not (is_publish and _is_verified_user(sender))
                and not join_command
                and not (security_command and room and _room_manager(self, room, sender))):
            return False
        # A private command can be replayed by the Talkin transport with a new
        # frame/uid. Do not answer the same account-list request twice in a row.
        command_key = str(body or "").strip().casefold()
        if command_key in ("vi", "الموثقين", "الموثقون", "الموثقين؟"):
            now = time.time()
            seen_key = (_norm_user(sender), command_key, bool(is_private))
            previous = getattr(self, "_management_command_seen", {}).get(seen_key, 0.0)
            self._management_command_seen[seen_key] = now
            if previous and now - previous < 20.0:
                self.log("[DEDUP] ignored repeated account-list command")
                return True
        old_tracking = getattr(self._master_reply_local, "tracking", False)
        old_replied = getattr(self._master_reply_local, "replied", False)
        old_private_replied = getattr(self._master_reply_local, "private_replied", False)
        old_command_private = getattr(self._master_reply_local, "command_private", True)
        old_command_sender = getattr(self._master_reply_local, "command_sender", "")
        old_command_room = getattr(self._master_reply_local, "command_room", "")
        self._master_reply_local.tracking = True
        self._master_reply_local.replied = False
        self._master_reply_local.private_replied = False
        self._master_reply_local.command_private = bool(is_private)
        self._master_reply_local.command_sender = sender
        self._master_reply_local.command_room = room
        try:
            handled = self._handle_management_command_impl(room, body, sender, is_private=is_private)
            if handled and _is_master_name(sender):
                if is_private and not self._master_reply_local.private_replied:
                    self.send_private_text(sender, f"✅ تم تنفيذ الأمر: {str(body or '').strip()}")
                elif not is_private and not self._master_reply_local.replied:
                    self.send_room_text(room, f"✅ تم تنفيذ الأمر: {str(body or '').strip()}")
            return handled
        finally:
            self._master_reply_local.tracking = old_tracking
            self._master_reply_local.replied = old_replied
            self._master_reply_local.private_replied = old_private_replied
            self._master_reply_local.command_private = old_command_private
            self._master_reply_local.command_sender = old_command_sender
            self._master_reply_local.command_room = old_command_room

    def _handle_management_command_impl(self, room, body, sender, is_private=False):
        """Giant-style persistent management commands. Returns True if consumed."""
        text=str(body or "").strip()
        low=text.casefold()
        if low in ("تشغيل الحماية", "تشغيل الحمايه", "الحماية تشغيل", "الحمايه تشغيل"):
            if not room or not _room_manager(self, room, sender):
                return True
            cfg = _save_room_moderation(room, enabled=True)
            self.send_room_text(room, f"🛡️ حماية الغرفة شغالة. حد التكرار: {cfg['repeat_limit']} رسائل.")
            return True
        if low in ("إيقاف الحماية", "ايقاف الحماية", "إيقاف الحمايه", "ايقاف الحمايه", "الحماية إيقاف", "الحمايه ايقاف"):
            if not room or not _room_manager(self, room, sender):
                return True
            _save_room_moderation(room, enabled=False)
            self.send_room_text(room, "⛔ حماية الغرفة متوقفة.")
            return True
        m_repeat = re.fullmatch(r"mr@(\d+)", text, re.I)
        if m_repeat:
            if not room or not _room_manager(self, room, sender):
                return True
            limit = max(2, min(50, int(m_repeat.group(1))))
            _save_room_moderation(room, repeat_limit=limit)
            self.send_room_text(room, f"✅ تم ضبط حماية التكرار في {room} على {limit} رسائل متتالية.")
            return True
        if low in ("نسخ احتياطي", "نسخه احتياطيه", "backup", "full backup"):
            queued = _request_github_full_backup(self, sender)
            if queued:
                self.send_private_text(
                    sender,
                    f"⏳ بدأ النسخ الاحتياطي في الخلفية. سيتم تأكيد النجاح بعد رفع {queued} ملفاً إلى GitHub (Talkin4)."
                )
            else:
                self.send_private_text(sender, "⚠️ تعذر بدء النسخ الاحتياطي؛ تأكد من تفعيل GITHUB_SYNC وإعداد مستودع Talkin4.")
            return True
        # Master-only self restart. The reply stays in the same channel where
        # the master issued the command, then the current Python process is replaced.
        if low in ("اعاده تشغيل البوت", "اعادة تشغيل البوت", "إعاده تشغيل البوت", "إعادة تشغيل البوت", "restart bot", "restart"):
            reply = "🔄 جاري إعادة تشغيل البوت..."
            if is_private:
                self.send_private_text(sender, reply)
            elif room:
                self.send_room_text(room, reply)
            else:
                self.send_private_text(sender, reply)

            def _restart_process():
                try:
                    time.sleep(1.2)
                    self.stop_event.set()
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception as exc:
                    self.log("[BOT] restart failed:", repr(exc))
                    try:
                        self.stop_event.clear()
                        if is_private:
                            self.send_private_text(sender, f"❌ تعذر إعادة تشغيل البوت: {exc}")
                        elif room:
                            self.send_room_text(room, f"❌ تعذر إعادة تشغيل البوت: {exc}")
                    except Exception:
                        pass

            threading.Thread(target=_restart_process, name="bot-restart", daemon=True).start()
            return True
        # `اوامر` shows the organized menu only.
        if low in ("اوامر الماستر", "اوامر_الماستر"):
            if not _is_master_name(sender):
                return False
            target = sender if is_private else None
            menu = _command_menu_for(True, is_private=is_private)
            if target:
                self.send_private_text(target, menu)
            else:
                self.send_room_text(room, menu)
            return True
        if low in ("اوامر","الاوامر","help","مساعدة"):
            target = sender if is_private else None
            menu = _command_menu_for(_is_master_name(sender), is_private=is_private)
            if target:
                self.send_private_text(target, menu)
            else:
                self.send_room_text(room, menu)
            return True
        m_help = re.fullmatch(r"help([1-6])", low)
        if m_help:
            page=int(m_help.group(1))
            if page == 1 and (not _is_master_name(sender) or not is_private):
                return True
            key=(str(room), _norm_user(sender))
            self.help_pages[key]=page
            self.help_page_part[key]=1
            self.help_game_part[key]=1
            self._send_help(room=room, private_to=sender if is_private else None, page=page, game_part=1)
            return True
        if low in ("ns","n","التالي","القائمة التالية","next"):
            key=(str(room), _norm_user(sender))
            current_page=int(self.help_pages.get(key,1) or 1)
            sections = _help_sections_from_messages().get(current_page, [])
            total = max(1, len(sections))
            part = int(self.help_page_part.get(key, self.help_game_part.get(key,1)) or 1)
            part = (part % total) + 1
            self.help_page_part[key]=part
            self.help_game_part[key]=part
            self._send_help(room=room, private_to=sender if is_private else None, page=current_page, game_part=part)
            return True
        if low in ("نقاطي","points"):
            self.send_private_text(sender, _points_summary_text(sender))
            return True
        mtop=re.fullmatch(r"توب\s*(رهان|مضاربة|حظي|استثمار)?", low)
        if low in ("توب","top") or mtop:
            game_label=mtop.group(1) if mtop else None
            game_map={"رهان":"bet","مضاربة":"duel","حظي":"luck","استثمار":"investment"}
            if game_label:
                rows=_game_top(game_map[game_label])
                msg=f"🏆 توب {game_label}\n━━━━━━━━━━━━\n" + ("\n".join(f"{i}. @{u} — {_fmt_points(p)} نقطة | {pl} لعب" for i,(p,st,pl,u) in enumerate(rows,1)) if rows else "لا توجد نتائج بعد.")
            else:
                data=_points_data(); rows=[]
                for v in data.values():
                    try: rows.append((int(v.get("points",0)),v.get("username", "")))
                    except Exception: pass
                rows.sort(reverse=True)
                msg="🏆 توب النقاط\n━━━━━━━━━━━━\n"+"\n".join(f"{i}. @{u} — {_fmt_points(p)}" for i,(p,u) in enumerate(rows[:10],1)) if rows else "🏆 لا توجد نقاط بعد."
            if is_private: self.send_private_text(sender,msg)
            else: self.send_room_text(room,msg)
            return True
        # Word-filter controls are master-only and persist in moderation.json.
        if low == "mf@on" or low == "mf@off" or low.startswith("+mf@") or low.startswith("-mf@") or low == "l@mf" or low == "clear@mf":
            if not _is_master_name(sender):
                return True
            if low == "mf@on":
                self.moderation_enabled = True
                _save_moderation_config(True, sorted(self.banned_words))
                return True
            if low == "mf@off":
                self.moderation_enabled = False
                _save_moderation_config(False, sorted(self.banned_words))
                return True
            if low.startswith("+mf@"):
                word = text[4:].strip()
                if word:
                    self.banned_words.add(word)
                    _save_moderation_config(self.moderation_enabled, sorted(self.banned_words))
                    _save_mf_config(self.moderation_enabled, sorted(self.banned_words))
                    self.log("[FILTER] saved to mf.json:", word)
                return True
            if low.startswith("-mf@"):
                word = text[4:].strip()
                target_norm = _norm_filter_text(word)
                self.banned_words = {w for w in self.banned_words if _norm_filter_text(w) != target_norm}
                _save_moderation_config(self.moderation_enabled, sorted(self.banned_words))
                _save_mf_config(self.moderation_enabled, sorted(self.banned_words))
                return True
            if low == "clear@mf":
                self.banned_words.clear()
                _save_moderation_config(self.moderation_enabled, [])
                _save_mf_config(self.moderation_enabled, [])
                return True
            if low == "l@mf":
                # Deliberately silent for master commands; list is available in moderation.json.
                self.log("[FILTER] words=", sorted(self.banned_words))
                return True

        # Joining a room: ONLY the master command دخول@اسم_الغرفة is accepted.
        m_join = re.fullmatch(r"دخول@(.+)", text, re.I)
        if m_join:
            target = m_join.group(1).strip()
            if not target:
                self.send_private_text(sender, "❌ الصيغة: دخول@اسم_الغرفة"); return True
            blocked = _norm_room(target) in getattr(self, "blocked_rooms", set())
            joined = self.join_room(target)
            if blocked:
                reply = f"🚫 البوت محظور من الغرفة {target}. أعطِ البوت إشرافاً أو أونر ثم أعد المحاولة: دخول@{target}"
            else:
                reply = f"{'✅ تم طلب دخول الغرفة' if joined else '⚠️ الغرفة متصلة بالفعل'}: {target} | المتصلة فعلياً: {len(self.connected_rooms)}"
            self.send_private_text(sender, reply)
            return True
        m_transfer = re.fullmatch(r"sb@([^@]+)@(\d+)", text, re.I)
        if m_transfer and _is_verified_user(sender):
            target, amount = m_transfer.group(1).strip().lstrip("@"), int(m_transfer.group(2))
            if not target or amount <= 0:
                self.send_private_text(sender, "❌ الصيغة: sb@اسم المستخدم@عدد النقاط")
                return True
            if not _is_primary_master(sender):
                balance = _get_points(sender)
                if balance < amount:
                    self.send_private_text(sender, f"❌ رصيدك غير كافٍ. رصيدك الحالي: {_fmt_points(balance)} نقطة.")
                    return True
                _add_points(sender, -amount)
            new = _add_points(target, amount)
            self.send_private_text(sender, f"✅ تم تحويل {_fmt_points(amount)} نقطة إلى @{target}. رصيدك: {_fmt_points(_get_points(sender))}")
            if _norm_user(target) != _norm_user(sender):
                self.send_private_text(target, f"💰 إشعار تحويل: استلمت {_fmt_points(amount)} نقطة من @{sender}. رصيدك الحالي: {_fmt_points(new)}")
            return True

        # VIP users may publish images; the actual image is handled by _handle_publish_media.
        if (low == "انشر" or low.startswith("انشر@")) and _is_vip_user(sender):
            desc=text[5:].strip() if low.startswith("انشر@") else ""
            self.publish_pending[_norm_user(sender)]={"description":desc,"source_room":str(room or ""),"created_at":time.time(),"silent":_is_master_name(sender)}
            self.send_private_text(sender,"🖼️ تم استلام أمر النشر. أرسل الصورة الآن خلال دقيقتين في الروم أو الخاص، وسيتم نشرها في جميع الغرف." + (f"\n📝 الوصف: {desc}" if desc else ""))
            return True

        if not _is_master_name(sender) and not (_is_mvip_master(sender) and _is_verification_manager_command(text)):
            if _looks_like_admin_command(text):
                self.send_private_text(sender, "🚫 هذا الأمر مخصص للماستر والإدارة فقط.")
            return False

        # "غرفي" must show only rooms that are actually connected in the
        # current WebSocket session. known_rooms is historical and may contain
        # rooms saved from an earlier run, so it must NOT be used here.
        if low in ("غرفي", "غرفيّ", "myrooms", "my rooms"):
            live = sorted({str(r).strip() for r in getattr(self, "connected_rooms", set()) if str(r).strip()})
            if not live:
                self.send_private_text(sender, "📭 لا توجد غرف متصلة فعلياً حالياً.")
            else:
                lines = [f"🏠 الغرف المتصلة فعلياً ({len(live)}):"]
                lines.extend(f"{i}. {room}" for i, room in enumerate(live, 1))
                self.send_private_text(sender, "\n".join(lines))
            return True

        m_all = re.fullmatch(r"تحويل للكل@(\d+)", text, re.I)
        if m_all:
            amount = int(m_all.group(1))
            if amount <= 0:
                self.send_private_text(sender, "❌ عدد النقاط يجب أن يكون أكبر من صفر.")
                return True
            users = {}
            active_rooms = {str(r).strip() for r in self.known_rooms if str(r).strip()}
            if self.room: active_rooms.add(str(self.room).strip())
            for active_room in active_rooms:
                for username in self.room_users.get(active_room, {}):
                    if username and _norm_user(username) != _norm_user(BOT_ID):
                        users[_norm_user(username)] = username
                try:
                    for item in self.db.room_users(active_room) or []:
                        username = str(item.get("username") or "").strip() if isinstance(item, dict) else ""
                        if username and _norm_user(username) != _norm_user(BOT_ID):
                            users[_norm_user(username)] = username
                except Exception as exc:
                    self.log("[POINTS-ALL] room roster failed:", active_room, repr(exc))
            for username in users.values():
                _add_points(username, amount)
                self.send_private_text(username, f"💰 إشعار تحويل جماعي: استلمت {_fmt_points(amount)} نقطة من الماستر @{sender}. رصيدك الحالي: {_fmt_points(_get_points(username))}")
            return True
            return True
        # Master commands are accepted from both private chat and rooms.
        # Room moderation acts on the room where the command was received.
        # Confirmations and diagnostics are sent privately to the master.
        if low in ("توثيق الكل", "وثق الكل", "verifyall", "verify_all", "vi@all", "vi@الكل"):
            users = {}
            active_rooms = {str(r).strip() for r in self.known_rooms if str(r).strip()}
            if self.room:
                active_rooms.add(str(self.room).strip())
            for active_room in active_rooms:
                for username in self.room_users.get(active_room, {}):
                    if username and _norm_user(username) != _norm_user(BOT_ID):
                        users[_norm_user(username)] = username
                try:
                    for item in self.db.room_users(active_room) or []:
                        username = str(item.get("username") or "").strip() if isinstance(item, dict) else ""
                        if username and _norm_user(username) != _norm_user(BOT_ID):
                            users[_norm_user(username)] = username
                except Exception as exc:
                    self.log("[VERIFY-ALL] room roster failed:", active_room, repr(exc))
            data = _verified_data()
            now = int(time.time())
            for username in users.values():
                data[_norm_user(username)] = {"username": username, "verified_by": sender, "created_at": now}
            _save_local_json(VERIFIED_FILE, data)
            self.send_private_text(sender, f"✅ تم توثيق {len(users)} مستخدم.")
            return True
        # Verification masters (persisted separately from management masters).
        if low.startswith("mvip@"):
            if not _is_primary_master(sender):
                self.send_private_text(sender, "🚫 إضافة ماستر توثيق مسموحة للمالك الأساسي فقط.")
                return True
            target = text[5:].strip().lstrip("@")
            if not target:
                self.send_private_text(sender, "❌ الصيغة: mvip@اسم المستخدم")
                return True
            data = _mvip_master_list()
            if any(_norm_user(x) == _norm_user(target) for x in data) or _is_master_name(target):
                self.send_private_text(sender, f"⚠️ @{target} لديه صلاحية ماستر توثيق بالفعل.")
                return True
            data.append(target)
            _save_local_json(MVIP_MASTERS_FILE, data)
            self.send_private_text(sender, f"✅ تم إضافة @{target} إلى ماسترات التوثيق.")
            return True
        if low.startswith("umvip@"):
            if not _is_primary_master(sender):
                self.send_private_text(sender, "🚫 إزالة ماستر توثيق مسموحة للمالك الأساسي فقط.")
                return True
            target = text[6:].strip().lstrip("@")
            data = [x for x in _mvip_master_list() if _norm_user(x) != _norm_user(target)]
            _save_local_json(MVIP_MASTERS_FILE, data)
            self.send_private_text(sender, f"✅ تم إزالة @{target} من ماسترات التوثيق.")
            return True
        if low == "l@mvip":
            if not _is_verification_manager(sender):
                return True
            msg = _format_saved_accounts("👑 ماسترات التوثيق", { _norm_user(x): {"username": x} for x in _mvip_master_list() }, "📭 لا توجد ماسترات توثيق.")
            self.send_private_text(sender, msg)
            return True
        if low == "l@mas":
            if not _is_master_name(sender):
                return True
            masters = list(_master_list())
            if BOT_MASTER and not any(_norm_user(x) == _norm_user(BOT_MASTER) for x in masters):
                masters.insert(0, BOT_MASTER)
            msg = _format_saved_accounts("👑 ماسترات الإدارة", { _norm_user(x): {"username": x} for x in masters }, "📭 لا توجد ماسترات إدارة.")
            self.send_private_text(sender, msg)
            return True

        # Add/remove master. Only the owner from BOT_MASTER may alter master list.
        if low.startswith("mas@"):
            if _norm_user(sender) != _norm_user(BOT_MASTER):
                self.log("[MASTER] add-master denied", sender); return True
            target=text[4:].strip().lstrip("@");
            if not target: self.log("[MASTER] invalid mas@", sender); return True
            masters=_master_list()
            if any(_norm_user(x)==_norm_user(target) for x in masters) or _norm_user(target) == _norm_user(BOT_MASTER):
                self.send_private_text(sender, f"⚠️ @{target} لديه صلاحية ماستر بالفعل.")
                return True
            masters.append(target); _save_local_json(MASTERS_FILE,masters)
            self.send_private_text(sender, f"✅ تم إضافة @{target} إلى الماسترز.")
            return True
        if low.startswith("umas@") or low.startswith("umas "):
            if _norm_user(sender) != _norm_user(BOT_MASTER):
                self.log("[MASTER] remove-master denied", sender); return True
            target=text[5:].strip().lstrip("@"); masters=[x for x in _master_list() if _norm_user(x)!=_norm_user(target)]; _save_local_json(MASTERS_FILE,masters)
            return True
        if low.startswith("sb@"):
            if not _is_master_name(sender):
                self.send_private_text(sender,"🚫 أمر النقاط للماستر فقط."); return True
            m=re.match(r"^sb@([^@]+)@(-?\d+)$",text,re.I)
            if not m: self.send_private_text(sender,"❌ الصيغة: sb@اسم المستخدم@عدد النقاط"); return True
            target,amount=m.group(1).strip(),int(m.group(2)); new=_add_points(target,amount)
            action = "تحويل" if amount >= 0 else "خصم"
            return True
            return True
        # Persistent account lists. These commands are master-only because
        # they expose the bot's saved verification records. They are read
        # directly from disk so replacing bot.py does not reset the lists.
        if low in ("vi", "الموثقين", "الموثقون", "الموثقين؟"):
            count = len(_verified_data())
            self.send_private_text(sender, f"📋 عدد الحسابات الموثقة: {count}")
            return True
        if low in ("vip", "vips", "حسابات vip", "قائمة vip"):
            count = len(_vip_data())
            self.send_private_text(sender, f"👑 عدد أعضاء VIP: {count}")
            return True
        if low in ("اعضاء", "أعضاء", "الاعضاء", "الأعضاء", "members"):
            users = _persistent_all_roster_users()
            self.send_private_text(sender, f"👥 عدد الأعضاء المحفوظين: {len(users)}")
            return True

        if low.startswith("vi@"):
            if not _is_verification_manager(sender):
                return True
            target=text[2:].strip().lstrip("@");
            if not target: self.send_private_text(sender,"❌ الصيغة: vi@اسم المستخدم"); return True
            data=_verified_data()
            key=_norm_user(target)
            if key in data:
                self.send_private_text(sender, f"⚠️ @{target} لديه توثيق عادي بالفعل.")
                return True
            if key in _vip_data():
                self.send_private_text(sender, f"⚠️ @{target} لديه توثيق VIP بالفعل.")
                return True
            data[key]={"username":target,"verified_by":sender,"created_at":int(time.time())}; _save_local_json(VERIFIED_FILE,data)
            # Keep the bot's normal verification notice for the verified user,
            # while the master process separately relays the result to whoever
            # requested the verification.
            self.send_private_text(target, f"✅ تم توثيق حسابك @{target} بنجاح.\n🎉 يمكنك الآن استخدام أوامر البوت.")
            self.send_private_text(sender, f"✅ تم توثيق @{target}.")
            return True
        if low.startswith("ازالة توثيق@") or low.startswith("إزالة توثيق@") or low.startswith("uns@"): 
            if not _is_verification_manager(sender):
                return True
            prefix="uns@" if low.startswith("uns@") else text.split("@",1)[0]+"@"
            target=text[len(prefix):].strip().lstrip("@"); data=_verified_data(); data.pop(_norm_user(target),None); _save_local_json(VERIFIED_FILE,data)
            self.send_private_text(sender, f"✅ تم إلغاء توثيق @{target}.")
            return True
        if low.startswith("vip@"):
            if not _is_verification_manager(sender):
                return True
            target=text[4:].strip().lstrip("@");
            if not target: self.send_private_text(sender,"❌ الصيغة: Vip@اسم المستخدم"); return True
            data=_vip_data(); key=_norm_user(target)
            if key in data:
                self.send_private_text(sender, f"⚠️ @{target} لديه توثيق VIP بالفعل.")
                return True
            data[key]={"username":target,"granted_by":sender,"created_at":int(time.time())}; _save_local_json(VIP_FILE,data)
            self.custom_welcomes[key] = {
                "username": target,
                "message": "👑 عضو Vip\n👤 {username}\n🏠 الغرفة: {room}"
            }
            self.custom_welcome_enabled = True
            self._save_social_features()
            for active_room in self._active_rooms():
                present = any(_norm_user(u) == key for u in self.room_users.get(active_room, {}))
                if present:
                    self.send_room_text(active_room, f"👑 عضو Vip\n👤 {target}\n🏠 الغرفة: {active_room}")
            self.send_private_text(target, f"✅ تم توثيق حسابك @{target}\n بنجاح.\n🎉 ويمكنك الان النشر وارسال الهدايا\n👑 تم تفعيل الترحيب المخصص تلقائياً.\nمن قبل @{sender}")
            self.send_private_text(sender, f"✅ تم منح VIP لـ @{target}.")
            return True
        if low.startswith("unvip@") or low.startswith("un vip@"):
            if not _is_verification_manager(sender):
                return True
            target=text[text.casefold().find("vip@")+4:].strip().lstrip("@"); data=_vip_data(); data.pop(_norm_user(target),None); _save_local_json(VIP_FILE,data)
            self.send_private_text(sender, f"✅ تم إلغاء VIP عن @{target}.")
            return True
        # Room/admin commands accepted in both room and private master chat.
        m=re.match(r"^(k@|kick\s+)(@?[^\s]+)$", text, re.I)
        if m:
            target=m.group(2).lstrip("@").strip()
            if not room:
                self.send_private_text(sender,"❌ لا توجد غرفة لتنفيذ الطرد فيها."); return True
            self.request_admin_action(room,target,"kick",sender)
            return True
        m=re.match(r"^(b@|ban\s+)(@?[^\s]+)$", text, re.I)
        if m:
            target=m.group(2).lstrip("@").strip()
            if not room:
                self.send_private_text(sender,"❌ لا توجد غرفة لتنفيذ الحظر فيها."); return True
            self.request_admin_action(room,target,"ban",sender)
            return True
        m=re.match(r"^bl@(.+)$", text, re.I)
        if m:
            target=m.group(1).strip().lstrip("@")
            active_rooms={str(r).strip() for r in self.known_rooms if str(r).strip()}
            if self.room: active_rooms.add(str(self.room).strip())
            active_rooms.discard("")
            if not active_rooms:
                self.send_private_text(sender,"❌ البوت غير موجود في أي غرفة حالياً."); return True
            for active_room in sorted(active_rooms):
                # The master command is authoritative: announce immediately
                # in every room, without waiting for a server role_changed
                # event or confirmation timeout.
                self.send_room_text(active_room, f"🚫 @{target} تم حظره بسبب الإساءة.")
                self.request_admin_action(active_room, target, "ban", sender)
            return True
        m=re.match(r"^(u@|ub@|unban\s+)(@?[^\s]+)$", text, re.I)
        if m:
            target=m.group(2).lstrip("@").strip()
            if not room:
                self.send_private_text(sender,"❌ لا توجد غرفة لتنفيذ فك الحظر فيها."); return True
            self.request_admin_action(room,target,"member",sender)
            return True
        m=re.match(r"^(a@|admin\s+)(@?[^\s]+)$", text, re.I)
        if m:
            target=m.group(2).lstrip("@").strip()
            if not room:
                self.send_private_text(sender,"❌ لا توجد غرفة لتعيين المشرف فيها."); return True
            self.request_admin_action(room,target,"admin",sender)
            return True
        m=re.match(r"^(o@|owner\s+)(@?[^\s]+)$", text, re.I)
        if m:
            target=m.group(2).lstrip("@").strip()
            if not room:
                self.send_private_text(sender,"❌ لا توجد غرفة لتعيين المالك فيها."); return True
            self.request_admin_action(room,target,"owner",sender)
            return True
        m_join = re.fullmatch(r"دخول@(.+)", text, re.I)
        if m_join:
            target=m_join.group(1).strip()
            if not target:
                self.send_private_text(sender,"❌ الصيغة: دخول@اسم_الغرفة"); return True
            self.join_room(target)
            self.send_private_text(sender,f"✅ دخلت الغرفة: {target} | الغرف الحالية: {len(self.known_rooms)}"); return True
        if low in ("خروج","leave","exit") or low.startswith(("خروج ","leave ","exit ")):
            parts=text.split(None,1); target=parts[1].strip() if len(parts)==2 else ""
            if target:
                ok=self.leave_room(target)
                self.send_private_text(sender,f"{'✅ خرجت من الغرفة' if ok else '❌ تعذر الخروج'}: {target}")
            else:
                rooms=self.leave_all_rooms()
                self.send_private_text(sender,f"✅ خرجت من جميع الغرف. العدد: {len(rooms)}")
            return True
        if low.startswith("invmsg") or low.startswith("رسالةدعوة"):
            parts=text.split(None,1); template=parts[1].strip() if len(parts)==2 else "🎁 لديك معجب مجهول 👥 في غرفة: {room}"
            self.invite_message_template=template
            self.send_private_text(sender,f"✅ تم تغيير نص الدعوة إلى: {template}"); return True
        if low == "inv" or low.startswith("inv ") or low in ("دعوات","invite") or low.startswith(("دعوات ","invite ")):
            # Invitations are executed only from the room where the command is sent.
            if is_private or not room:
                self.send_private_text(sender, "⚠️ نفّذ inv داخل الغرفة المطلوبة.")
                return True
            target_room = str(room).strip()
            role_ok = self._inv_bot_owner_allowed(target_room)
            if role_ok is False:
                self.send_room_text(target_room, "⚠️ ارفع البوت أونر راعد المحاولة.")
                return True
            if role_ok is None:
                self._pending_inv_role_check[_norm_room(target_room)] = {
                    "sender": sender, "room": target_room,
                }
                self.send_room_text(target_room, "⏳ جاري التحقق من رتبة البوت...")
                return True
            self.request_occupants(
                target_room,
                silent_master=False,
                response_room=target_room,
                response_to="",
            )
            return True
        m_single_invite = re.fullmatch(r"i@(.+)", text.strip(), re.I)
        if m_single_invite:
            target = m_single_invite.group(1).strip().lstrip("@")
            target_room = str(room or self.room or "").strip()
            if not target or not target_room:
                self.send_private_text(sender, "❌ الصيغة: i@اسم_المستخدم داخل غرفة.")
                return True
            try:
                msg = f"✅ تم إرسال دعوة @{target} إلى الغرفة {target_room}." if sent else f"⚠️ الدعوة @{target} أُرسلت سابقًا أو تعذر إرسالها."
                if is_private:
                    self.send_private_text(sender, msg)
                else:
                    self.send_room_text(room, msg)
            except Exception as exc:
                msg = f"❌ تعذر إرسال الدعوة إلى @{target}: {exc}"
                if is_private:
                    self.send_private_text(sender, msg)
                else:
                    self.send_room_text(room, msg)
            return True
        if low.startswith("say ") or low.startswith("قل "):
            parts=text.split(None,1); msg=parts[1].strip() if len(parts)==2 else ""
            if room and msg: self.send_room_text(room,msg)
            else: self.send_private_text(sender,"❌ استخدم say نص داخل غرفة.")
            return True
        # Auto replies: +sr@وصف@الرد / Sr@on / Sr@off
        m_sr = re.match(r"^\+sr@([^@]+)@(.+)$", text.strip(), re.I)
        if m_sr and _is_master_name(sender):
            trigger, reply = m_sr.group(1).strip(), m_sr.group(2).strip()
            if trigger and reply:
                self.auto_replies[trigger.casefold()] = {"trigger": trigger, "reply": reply}
                self.auto_replies_enabled = True
                self._save_social_features()
                self.send_private_text(sender, f"✅ تمت إضافة الرد التلقائي\n📌 الوصف: {trigger}\n💬 الرد: {reply}")
            return True
        if re.match(r"^sr@(?:on|off)$", text.strip(), re.I) and _is_master_name(sender):
            self.auto_replies_enabled = text.strip().lower() == "sr@on"
            self._save_social_features()
            self.send_private_text(sender, "✅ تم تشغيل الردود التلقائية." if self.auto_replies_enabled else "⛔ تم إيقاف الردود التلقائية.")
            return True
        # Custom welcome: swc+@اسم@الترحيب and on/off.
        m_sw = re.match(r"^(?:swc\+|ترحيب\+)@([^@]+)@(.+)$", text.strip(), re.I)
        if m_sw and _is_master_name(sender):
            user, welcome = m_sw.group(1).strip().lstrip("@"), m_sw.group(2).strip()
            if user and welcome:
                self.custom_welcomes[_norm_user(user)] = {"username": user, "message": welcome}
                self.custom_welcome_enabled = True
                self._save_social_features()
                self.send_private_text(sender, f"✅ تم حفظ الترحيب المخصص لـ @{user}.\n💬 {welcome}")
            return True
        if re.match(r"^swc@(?:on|off)$", text.strip(), re.I) and _is_master_name(sender):
            self.custom_welcome_enabled = text.strip().lower() == "swc@on"
            self._save_social_features()
            self.send_private_text(sender, "✅ تم تشغيل الترحيب المخصص." if self.custom_welcome_enabled else "⛔ تم إيقاف الترحيب المخصص.")
            return True
        # Publishing: master or verified user says `انشر` or `انشر@description`, then sends an image.
        if low == "انشر" or low.startswith("انشر@"):
            desc=text[5:].strip() if low.startswith("انشر@") else ""
            # The image may be sent later in a room or in private chat.
            # Key the pending publish by sender, not by the command room, so
            # sending the image from another room still completes the publish.
            self.publish_pending[_norm_user(sender)]={"description":desc,"source_room":str(room or ""),"created_at":time.time(),"silent":False}
            self.send_private_text(sender,"🖼️ تم استلام أمر النشر. أرسل الصورة الآن خلال دقيقتين في الروم أو الخاص، وسيتم نشرها في جميع الغرف." + (f"\n📝 الوصف: {desc}" if desc else ""))
            return True
        return False

    def _handle_publish_media(self, room, sender, media_url, description=""):
        if not media_url: return False
        # Accept the pending image from ANY room (or private chat).
        key=_norm_user(sender); pending=self.publish_pending.get(key)
        if not pending: return False
        if time.time()-pending.get("created_at",0)>120:
            self.publish_pending.pop(key,None); self.send_private_text(sender,"⌛ انتهت مهلة النشر، أرسل أمر انشر من جديد."); return True
        desc=pending.get("description",description or "")
        source_room=str(pending.get("source_room") or room or "")
        silent_publish=bool(pending.get("silent"))
        self.publish_pending.pop(key,None)
        # A room that rejected/banned the bot must not abort or receive this
        # publication; all other active rooms continue normally.
        rooms=self._active_rooms()
        # In rooms, the successful publish message contains ONLY the reaction
        # controls. The publish status/result is sent privately to the master.
        base_code=uuid.uuid4().hex[:4]
        reaction_codes={
            "like": base_code,
            "love": uuid.uuid4().hex[:4],
            "dislike": uuid.uuid4().hex[:4],
            "comment": uuid.uuid4().hex[:4],
            "report": uuid.uuid4().hex[:4],
        }
        for kind,code in reaction_codes.items():
            self.reaction_targets[code]={"publisher": sender, "kind": kind, "description": desc or "منشور صورة", "created_at": time.time()}
        caption=_message_template(
            "publish", "broadcast",
            "🖼️ {description}\n👤 {publisher}\n━━━━━━━━━━━━━\n👍 lk@{like}\n❤️ lv@{love}\n👎 dl@{dislike}\n💬 cm@{comment} msg\n🚨 report@{report} msg",
            publisher=sender, description=desc or "منشور صورة",
            source_label=source_room, code=base_code,
            like=reaction_codes["like"], love=reaction_codes["love"], dislike=reaction_codes["dislike"],
            comment=reaction_codes["comment"], report=reaction_codes["report"], room=source_room
        )
        ok=0
        errors=[]
        for target in rooms:
            try:
                self.send_room_media(target,media_url,"image")
                self.send_room_text(target,caption)
                ok+=1
            except Exception as e:
                errors.append((target,str(e)))
                self.log("[PUBLISH] failed",target,repr(e))
        # Master publish commands may be silent; public publication itself remains active.
        if not silent_publish:
            self.send_private_text(sender,f"✅ تم نشر الصورة في {ok} غرفة." + (f"\n❌ أخطاء: {len(errors)}" if errors else ""))
            if errors:
                self.send_private_text(sender, "❌ أخطاء النشر: " + " | ".join(f"{r}: {e[:60]}" for r,e in errors))
        return True

    def _is_duplicate_incoming(self, kind, values, event_id=""):
        """Return True when the server has replayed an inbound event.

        Event id 41 is preferred. Some Talkin server versions omit it, so a
        short-lived content signature is used as a fallback. The cache is
        intentionally in memory: it is transport de-duplication state, not
        bot data that should be persisted to GitHub.
        """
        now = time.time()
        event_id = str(event_id or "").strip()
        if event_id:
            key = (str(kind), "id", event_id)
            ttl = 300.0
        else:
            raw = "\x1f".join(str(v or "") for v in values)
            key = (str(kind), "sig", hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest())
            ttl = 8.0
        with self._incoming_seen_lock:
            previous = self._incoming_seen.get(key, 0.0)
            self._incoming_seen[key] = now
            if len(self._incoming_seen) > 2000:
                cutoff = now - 300.0
                self._incoming_seen = {k: ts for k, ts in self._incoming_seen.items() if ts >= cutoff}
        return bool(previous and now - previous < ttl)

    def handle_room_event(self, result):
        event = result.get("room_event") or {}
        if not hasattr(self, "blocked_rooms"):
            self.blocked_rooms = set()
        if not hasattr(self, "_blocked_room_notices"):
            self._blocked_room_notices = set()
        event_type = str(event.get(1, ""))
        frm = str(event.get(2, ""))
        to = str(event.get(3, ""))
        body = str(event.get(6, ""))
        room = str(event.get(13, self.room))
        if room and room != BOT_MASTER:
            self.known_rooms.add(room)
            self.connected_rooms.add(room)
            _save_persistent_rooms(self.known_rooms)
        event_id = str(event.get(41, ""))
        username = str(event.get(22, "") or "").strip()
        role = str(event.get(8, "") or "").strip().lower()
        count = str(event.get(23, "") or "").strip()
        reconnected = str(event.get(24, "") or "").strip()
        # Do not log room message contents, usernames, room names, or media events.
        if self._is_duplicate_incoming(
            "room",
            (event_type, room, frm, to, body, str(event.get(7, "") or "")),
            event_id,
        ):
            self.log("[DEDUP] ignored repeated room event")
            return

        # Keep the live membership state in sync.  The APK itself uses these
        # exact event names and RoomEvent fields.
        if event_type == "user_joined" and username:
            self.room_users[room][username] = role or "none"
            _remember_roster(room, [{"username": username, "role": role or "none"}])
            self.last_joined_room = room
            if _norm_user(username) == _norm_user(BOT_MASTER):
                self._master_online_rooms.add(_norm_room(room))
                self.master_online = True
                self.master_last_seen = time.time()
            # Welcome the master using the exact configured BOT_MASTER account.
            if _norm_user(username) == _norm_user(BOT_MASTER):
                self.send_room_text(room, f"👑 لقد أتاكم الزعيم\n👤 {username}\n🏠 الغرفة: {room}")
            elif self.custom_welcome_enabled:
                cw = self.custom_welcomes.get(_norm_user(username))
                if _is_vip_user(username):
                    cw = {"message": "👑 عضو Vip\n👤 {username}\n🏠 الغرفة: {room}"}
                if isinstance(cw, dict) and cw.get("message"):
                    self.send_room_text(room, str(cw["message"]).replace("{username}", username).replace("{room}", room))
        elif event_type == "user_left" and username:
            self.room_users[room].pop(username, None)
            if _norm_user(username) == _norm_user(BOT_MASTER):
                self._master_online_rooms.discard(_norm_room(room))
                self.master_online = bool(self._master_online_rooms)
        elif event_type == "role_changed":
            # In native RoomEvent packets the affected user is field 17 and
            # the resulting role is field 31. Field 8 is not reliable here.
            changed_user = str(event.get(17, "") or event.get(22, "") or "").strip()
            changed_role = str(event.get(31, "") or event.get(8, "") or "").strip().lower()
            if changed_user and changed_role:
                if changed_role in ("kicked", "outcast"):
                    self.room_users[room].pop(changed_user, None)
                else:
                    self.room_users[room][changed_user] = changed_role
                key = (room.casefold(), changed_user.casefold(), changed_role)
                with self.pending_admin_lock:
                    pending = self.pending_admin_actions.pop(key, None)
                if pending:
                    labels = {
                        "kicked": f"✅ أكد الخادم طرد @{changed_user} من الغرفة {room}.",
                        "outcast": f"✅ أكد الخادم حظر @{changed_user} في الغرفة {room}.",
                        "member": f"✅ أكد الخادم فك حظر @{changed_user} في الغرفة {room}.",
                        "admin": f"✅ أكد الخادم ترقية @{changed_user} إلى مشرف في الغرفة {room}.",
                        "owner": f"✅ أكد الخادم ترقية @{changed_user} إلى مالك في الغرفة {room}.",
                    }
                    # The command already reports success immediately. Keep the
                    # native event only for state synchronization and logging.
                    # Keep master moderation silent; confirmation is logged only.
                    self.log(f"[MOD] server confirmed room={room} target=@{changed_user} role={changed_role}")
        elif event_type in ("you_joined", "you_rejoined"):
            self.last_joined_room = room
            rnorm = _norm_room(room)
            self._pending_room_joins.pop(rnorm, None)
            self.blocked_rooms.discard(rnorm)
            self._blocked_room_reasons.pop(rnorm, None)
            self._blocked_room_notices.discard(rnorm)
            self._save_blocked_rooms()
        elif event_type in ("room_full_rejoin", "room_unauthorized_rejoin", "room_wrong_password_rejoin", "room_needs_captcha_rejoin", "room_needs_password_rejoin", "room_membership_required_rejoin"):
            # IMPORTANT: do not immediately send room_join here.  These events
            # can be emitted repeatedly by the server when a room rejects a
            # join.  The old code answered every event with another room_join,
            # creating the visible leave/join loop.  A real reconnect is left
            # to run_once(), while a rejoin is attempted at most once after a
            # long cooldown and never recursively from this event handler.
            self.log("[ROOM] server requested rejoin; delayed reconnect")
            failure_events = {"room_unauthorized_rejoin", "room_membership_required_rejoin", "room_full_rejoin", "room_wrong_password_rejoin", "room_needs_password_rejoin", "room_needs_captcha_rejoin"}
            if event_type in failure_events:
                blocked_room = _norm_room(room)
                reason_text = self._room_failure_message(room, event_type)
                self._pending_room_joins.pop(blocked_room, None)
                self._mark_room_blocked(room, reason_text)
                if event_type == "room_unauthorized_rejoin":
                    advice = "ارفع البوت إشرافاً أو أونر ثم أعد المحاولة."
                elif event_type == "room_membership_required_rejoin":
                    advice = "الغرفة للأعضاء فقط؛ أضف البوت للغرفة ثم أعد المحاولة."
                elif event_type == "room_full_rejoin":
                    advice = "الغرفة ممتلئة؛ فرّغ مقعداً ثم أعد المحاولة."
                elif event_type in ("room_wrong_password_rejoin", "room_needs_password_rejoin"):
                    advice = "تأكد من كلمة مرور الغرفة ثم أعد المحاولة."
                else:
                    advice = "الغرفة تطلب تحققاً لا يستطيع البوت إكماله آلياً."
                notice=f"{reason_text}: {room}\n💡 {advice}"
                recipient=username if username and _norm_user(username) != _norm_user(BOT_ID) else BOT_MASTER
                if recipient and blocked_room not in self._blocked_room_notices:
                    self.send_private_text(recipient, notice)
                    self._blocked_room_notices.add(blocked_room)
                if BOT_MASTER and _norm_user(recipient) != _norm_user(BOT_MASTER):
                    self.send_private_text(BOT_MASTER, f"⚠️ تعذر دخول البوت غرفة: {room}\n{reason_text}\nتم وضعها في الاستثناءات ولن يحاول الدخول إليها تلقائياً.")

        if ACK_ROOM_EVENTS and result.get("uid"):
            try:
                self.ack(result["uid"])
            except Exception as e:
                self.log("[ACK] failed:", e)

        # A photo sent in a room arrives as RoomEvent type=image with its
        # public URL in field 7 (url). If a master previously used `انشر`,
        # publish that image even when it was sent from a different room.
        if event_type == "image":
            media_url = str(event.get(7, "") or "").strip()
            if frm and frm != BOT_ID and media_url:
                # Ignore ordinary room images silently. Only a pending publish
                # request may consume an image, avoiding verification notices.
                if _is_verified_user(frm) and self._handle_publish_media(room, frm, media_url):
                    return
            return

        if event_type != "text" or not body:
            return
        if frm == BOT_ID:
            return

        # Administrative commands are private to the configured master. Do
        # not send an authorization message to other users and do not allow
        # verified/VIP users to reach the management handlers accidentally.
        is_publish_command = body.strip().casefold() == "انشر" or body.strip().casefold().startswith("انشر@")
        if (_looks_like_admin_command(body)
                and not _is_master_name(frm)
                and not (_is_mvip_master(frm) and _is_verification_manager_command(body))
                and not (re.fullmatch(r"sb@([^@]+)@(\d+)", body.strip(), re.I) and _is_verified_user(frm))
                and not (is_publish_command and _is_verified_user(frm))):
            if not _is_verified_user(frm):
                self.send_room_text(room, f"🔒 @{frm} طلب توثيق لاستخدام أوامر البوت.\n{_verification_notice()}")
            return

        # Word filter runs before games/normal commands. It uses the same native
        # room ban operation as b@, with Arabic normalization and no public reply.
        room_cfg = _room_moderation_config(room)
        if room_cfg["enabled"] and not _is_master_name(frm):
            now = time.time()
            state = self._room_repeat_state[room]
            last_sender = str(state.get("sender", ""))
            last_text = str(state.get("text", ""))
            last_at = float(state.get("at", 0.0) or 0.0)
            same_sender = _norm_user(last_sender) == _norm_user(frm)
            same_text = _norm_filter_text(last_text) == _norm_filter_text(body.strip())
            within_window = now - last_at <= 30.0
            # Both counters are consecutive counters. A different sender
            # breaks the sender sequence; a different text breaks the text
            # sequence. Either counter can independently cause a ban.
            state["sender_count"] = int(state.get("sender_count", 0) or 0) + 1 if same_sender and within_window else 1
            state["text_count"] = int(state.get("text_count", 0) or 0) + 1 if same_text and within_window else 1
            state["sender"] = frm
            state["text"] = body.strip()
            state["at"] = now
            sender_count = int(state.get("sender_count", 0) or 0)
            text_count = int(state.get("text_count", 0) or 0)
            limit = room_cfg["repeat_limit"]
            if sender_count >= limit or text_count >= limit:
                self.send_admin(room, frm, "ban")
                self.send_room_text(room, f"🚫 تم حظر @{frm}\nالسبب: تكرار مشبوه")
                state.clear()
                return
            if sender_count == limit - 1 or text_count == limit - 1:
                self.send_room_text(room, f"⚠️ تحذير @{frm}: الرسالة مكررة، الرسالة التالية ستؤدي إلى الحظر.")
                return
        filter_words = room_cfg["words"] or (sorted(self.banned_words) if self.moderation_enabled else [])
        normalized_body = _norm_filter_text(body)
        hit = next((w for w in filter_words if _norm_filter_text(w) and _norm_filter_text(w) in normalized_body), None)
        if hit and not _is_master_name(frm):
            try:
                self.send_admin(room, frm, "ban")
                self.send_room_text(room, f"🚫 تم حظر @{frm}\nالسبب: كلمة مسيئة")
                self.log("[WORD-FILTER] native room ban", frm, "word=", hit, "room=", room)
            except Exception as exc:
                self.log("[WORD-FILTER] failed:", repr(exc))
            return

        # شبيه: متاح كأمر غرفة مستقل ولا يحتاج توثيقاً.
        if self._handle_lookalike_command(room, body, frm):
            return

        # Reactions/comments/reports: notify the original publisher privately.
        reaction=re.match(r"^(lk|lv|dl|cm|report)@([A-Za-z0-9]{4})(?:\s+(.*))?$", body.strip(), re.I)
        if reaction:
            action,code,extra=reaction.group(1).lower(),reaction.group(2).lower(),(reaction.group(3) or "").strip()
            info=self.reaction_targets.get(code)
            if info and time.time()-float(info.get("created_at",0)) <= 86400:
                publisher=str(info.get("publisher") or "").strip()
                labels={"lk":"👍 إعجاب","lv":"❤️ حب","dl":"👎 عدم إعجاب","cm":"💬 تعليق","report":"🚨 بلاغ"}
                source_desc = str(info.get("description") or info.get("title") or "").strip()
                owner_label = "صاحب الأغنية" if str(info.get("kind") or "").lower() == "music" else "اسم الناشر"
                notice=f"لقد تفاعلت مع {labels.get(action,action)}\n👤 المتفاعل: {frm}\n📌 {owner_label}: {publisher}"
                if source_desc: notice += f"\n📝 المحتوى: {source_desc}"
                if extra: notice += f"\n💬 رسالة التفاعل: {extra}"
                # التفاعل يظهر داخل نفس الغرفة، وتصل نسخة مطابقة أيضاً
                # إلى صاحب الصورة/الأغنية على الخاص.
                self.send_room_text(room, notice)
                if publisher and _norm_user(publisher) != _norm_user(frm):
                    private_notice = notice + f"\n🏠 الغرفة: {room}"
                    self.send_private_text(publisher, private_notice)
                return

        # نقاطي متاح للجميع ولا يحتاج توثيقاً.
        if body.strip().casefold() in ("نقاطي", "points"):
            self.send_room_text(room, _points_summary_text(frm))
            return

        # Verified users may use normal bot commands; administration remains
        # restricted to masters. Unverified command attempts receive one clear
        # notice instead of being silently ignored.
        is_verified = _is_verified_user(frm)
        if not is_verified and _looks_like_bot_command(body) and not re.match(r"^دخول@.+$", body.strip(), re.I):
            self.send_room_text(room, f"🔒 @{frm} طلب توثيق لاستخدام أوامر البوت.\n{_verification_notice()}")
            return
        # Music/gifts require verification; masters are always allowed.
        if re.match(r"^sa@[^@]+@.+$", body.strip(), re.I):
            if not _is_verified_user(frm):
                self.send_room_text(room, f"🔒 @{frm} يحتاج توثيقاً لاستخدام الهدايا.\n{_verification_notice()}")
                return
            if self.handle_gift_command(room, body, frm):
                return
        if body.strip().casefold() in ("هدايا", "gifts", "gv"):
            self.gift_help(room)
            return
        m_share = re.fullmatch(r"sher@(.+)", body.strip(), re.I)
        if m_share:
            self.share_last_music(frm, m_share.group(1), room)
            return
        if body.strip().lower().startswith(".sa "):
            if not is_verified:
                self.send_room_text(room, f"🔒 @{frm} غير موثّق لاستخدام الأغاني.\n{_verification_notice()}")
                return
            if self.handle_music_command(room, body, frm):
                return

        # Keep a small per-room message history for diagnostics.
        self.last_messages[room].append((frm, body, event_id))
        self.last_messages[room] = self.last_messages[room][-50:]

        # Exact-match automatic replies.
        if self.auto_replies_enabled:
            ar = self.auto_replies.get(body.strip().casefold())
            if isinstance(ar, dict) and ar.get("reply"):
                reply = str(ar["reply"]).replace("{username}", frm).replace("{room}", room)
                self.send_room_text(room, reply)
                return

        if self._handle_management_command(room, body, frm):
            return

        if self.handle_game_command(room, body, frm):
            return

        if body.lower().strip() in ("!help", "مساعدة") and AUTO_HELP:
            self.send_room_text(room, "أوامر البوت: k@ اسم، b@ اسم، a@ اسم، o@ اسم، دخول@اسم_الغرفة، خروج [اسم_الغرفة]، inv، invmsg نص الدعوة لدعوة مستخدمي الغرفة")

    def _process_room_list(self, rooms):
        """Import the server room list after login/reconnect without joining it blindly."""
        found = set()
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = str(k).casefold()
                    if kl in ("name", "room", "room_name", "title") and isinstance(v, str) and v.strip():
                        found.add(v.strip())
                    walk(v)
            elif isinstance(obj, list):
                for v in obj: walk(v)
        walk(rooms)
        if not found:
            return
        blocked = {_norm_room(r) for r in self.blocked_rooms}
        found = {r for r in found if _norm_room(r) not in blocked}
        self.log("[ROOM-LIST] loaded", len(found), "rooms")
        # Keep the historical list so reconnect can restore rooms previously selected by the master.
        self.known_rooms.update(found)
        _save_persistent_rooms(self.known_rooms)

    def on_message(self, ws, message):
        try:
            if isinstance(message, str):
                self.log("[WS] unexpected text frame received")
                return
            result = decode_result_message(message)
            self._cache_user_photos_from_result(result)
            if "room_event" in result:
                self.handle_room_event(result)
            if result.get("rooms"):
                self._process_room_list(result.get("rooms"))
            if result.get("users") or result.get("room_admin"):
                self.process_occupants_for_invite(result)
            if result.get("stream_event"):
                self.log("[STREAM]", result["stream_event"])
            if result.get("room_admin"):
                self.log("[ROOM_ADMIN]", result["room_admin"])
            if result.get("chat_message"):
                # Private master commands are also accepted as ChatMessage frames.
                cm = result["chat_message"]
                try:
                    frm = str(cm.get(3, "") or "").strip()
                    body = str(cm.get(5, "") or "").strip()
                    media_url = str(cm.get(6, "") or "").strip()
                    if self._is_duplicate_incoming(
                        "private",
                        (frm, body, media_url),
                        str(cm.get(41, "") or result.get("uid", "") or ""),
                    ):
                        self.log("[DEDUP] ignored repeated private message")
                        return
                    if MASTER_SERVICE_ENABLED:
                        self._relay_private_to_owner(frm, body, media_url)
                    if _norm_user(frm) == _norm_user(BOT_MASTER):
                        self.master_online = True
                        self.master_last_seen = time.time()
                    if body and self._handle_master_process_command(frm, body, is_private=True):
                        return
                    # When this process is the master account, it owns the
                    # private service flow and performs verification itself.
                    if MASTER_SERVICE_ENABLED and self._handle_master_account_service(frm, body):
                        return
                    # When the master account is absent, the primary bot provides
                    # the private verification/support service. This must not depend
                    # on MASTER_SERVICE_ENABLED, because that flag is reserved for
                    # the standalone master process itself.
                    if not self._master_is_online() and self._handle_offline_master_service(frm, body):
                        return
                    if body and media_url:
                        if not _is_verified_user(frm):
                            self.send_room_text(self.room, f"🔒 @{frm} يحتاج توثيقاً لاستخدام النشر.\n{_verification_notice()}")
                            return
                        if self._handle_publish_media(self.room, frm, media_url):
                            return
                    # Silently ignore master-only commands from everyone else.
                    is_publish_command = body.strip().casefold() == "انشر" or body.strip().casefold().startswith("انشر@")
                    if (body and _looks_like_admin_command(body)
                            and not _is_master_name(frm)
                            and not (_is_mvip_master(frm) and _is_verification_manager_command(body))
                            and not (re.fullmatch(r"sb@([^@]+)@(\d+)", body.strip(), re.I) and _is_verified_user(frm))
                            and not (is_publish_command and _is_verified_user(frm))
                            and not re.match(r"^دخول@.+$", body, re.I)):
                        if not _is_verified_user(frm):
                            self.send_private_text(frm, f"🔒 @{frm} طلب توثيق لاستخدام أوامر البوت.\n{_verification_notice()}")
                        return
                    if body and not _is_verified_user(frm) and _looks_like_bot_command(body) and not re.match(r"^دخول@.+$", body.strip(), re.I):
                        self.send_room_text(self.room, f"🔒 @{frm} طلب توثيق لاستخدام أوامر البوت.\n{_verification_notice()}")
                        return
                    if body and body.casefold() in ("نقاطي", "points"):
                        self.send_private_text(frm, _points_summary_text(frm))
                        return
                    if body:
                        if self._handle_management_command(self.room, body, frm, is_private=True):
                            return
                    m_share = re.fullmatch(r"sher@(.+)", body.strip(), re.I)
                    if m_share:
                        self.share_last_music(frm, m_share.group(1))
                        return
                    if body.strip().lower().startswith(".sa "):
                        if self.handle_music_command(self.room, body, frm):
                            return
                    if re.match(r"^sa@[^@]+@.+$", body.strip(), re.I):
                        if _is_verified_user(frm):
                            if self.handle_gift_command(self.room, body, frm, private_to=frm):
                                return
                        else:
                            self.send_private_text(frm, f"🔒 @{frm} يحتاج توثيقاً لاستخدام الهدايا.\n{_verification_notice()}")
                            return
                    if body and _is_verified_user(frm) and self.handle_game_command(self.room, body, frm):
                        return
                    if _is_master_name(frm) and body:
                        # Reuse room command handling with the command-context room.
                        ctx_room = self.room
                        parts = body.split(None, 1)
                        cmd = parts[0].lower() if parts else ""
                        arg = parts[1].strip() if len(parts) == 2 else ""
                        if cmd in ("inv", "دعوات", "invite"):
                            if not ctx_room:
                                self.send_private_text(frm, "⚠️ نفّذ inv داخل الغرفة المطلوبة.")
                            else:
                                role_ok = self._inv_bot_owner_allowed(ctx_room)
                                if role_ok is False:
                                    self.send_private_text(frm, "⚠️ ارفع البوت أونر راعد المحاولة.")
                                elif role_ok is None:
                                    self._pending_inv_role_check[_norm_room(ctx_room)] = {"sender": frm, "room": ctx_room}
                                    self.send_private_text(frm, "⏳ جاري التحقق من رتبة البوت...")
                                else:
                                    self.request_occupants(ctx_room, silent_master=False, response_room=ctx_room)
                        elif re.fullmatch(r"دخول@(.+)", body.strip(), re.I):
                            target_room = re.fullmatch(r"دخول@(.+)", body.strip(), re.I).group(1).strip()
                            blocked_room = _norm_room(target_room)
                            was_blocked = blocked_room in self.blocked_rooms
                            self.blocked_rooms.discard(blocked_room)
                            self._blocked_room_notices.discard(blocked_room)
                            joined = self.join_room(target_room, force=True)
                            if joined:
                                self.send_private_text(BOT_MASTER, f"⏳ تم طلب دخول الغرفة: {target_room} | المتصلة فعلياً: {len(self.connected_rooms)}")
                            elif was_blocked:
                                self.send_private_text(BOT_MASTER, f"🚫 الغرفة {target_room} مسجلة كغرفة محظورة/غير متاحة. ارفع البوت إشرافاً أو أونر ثم أعد المحاولة.")
                            else:
                                self.send_private_text(BOT_MASTER, f"⚠️ تعذر طلب دخول الغرفة: {target_room}. تحقق من اسم الغرفة وصلاحية البوت.")
                        elif cmd in ("خروج", "leave", "exit"):
                            if arg:
                                ok = self.leave_room(arg)
                                self.send_private_text(BOT_MASTER, f"{'✅ خرجت من الغرفة' if ok else '❌ تعذر الخروج'}: {arg}")
                            else:
                                rooms = self.leave_all_rooms()
                                self.send_private_text(BOT_MASTER, f"✅ خرجت من جميع الغرف. العدد: {len(rooms)}")
                        elif cmd in ("invmsg", "رسالةدعوة") and arg:
                            self.invite_message_template = arg
                            self.send_private_text(frm, f"✅ تم تغيير رسالة الدعوة إلى: {arg}")
                        elif cmd in ("a@", "admin") and arg:
                            target = arg.lstrip("@").strip()
                            self.request_admin_action(ctx_room, target, "admin", frm)
                        elif cmd in ("o@", "owner") and arg:
                            target = arg.lstrip("@").strip()
                            self.request_admin_action(ctx_room, target, "owner", frm)
                        elif cmd in ("k@", "kick") and arg:
                            target = arg.lstrip("@").strip()
                            self.request_admin_action(ctx_room, target, "kick", frm)
                        elif cmd in ("b@", "ban") and arg:
                            target = arg.lstrip("@").strip()
                            self.request_admin_action(ctx_room, target, "ban", frm)
                        elif cmd in ("u@", "unban") and arg:
                            target = arg.lstrip("@").strip()
                            self.request_admin_action(ctx_room, target, "member", frm)
                        elif cmd in ("say", "قل") and arg:
                            self.send_room_text(ctx_room, arg)
                except Exception as e:
                    self.log("[CHAT_MESSAGE] private command handling failed:", repr(e))
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
        # These are rooms connected to THIS WebSocket session. Once it closes,
        # none of them may be reported by "غرفي" until the server confirms
        # them again after reconnect. The historical list remains on disk.
        self.connected_rooms.clear()
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

        # Keep every room selected by the master. A reconnect restores the
        # existing room set once; room-event handlers never leave/rejoin in a
        # loop, which avoids the visible leave/join cycle.
        blocked_norm = {_norm_room(r) for r in getattr(self, "blocked_rooms", set())}
        rooms_to_restore = set() if MASTER_SERVICE_ENABLED else {
            str(r).strip() for r in self.known_rooms
            if str(r).strip() and _norm_room(r) not in blocked_norm
        }
        if self.room and not MASTER_SERVICE_ENABLED:
            if _norm_room(self.room) not in blocked_norm:
                rooms_to_restore.add(str(self.room).strip())
        for room in sorted(rooms_to_restore):
            self.join_room(room, force=True)

    def run_once(self):
        # Start a fresh live-room view for this WebSocket session.
        self.connected_rooms.clear()
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
                        self._start_heartbeat()
                        self.log("[WS] CONNECTED:", url)
                        self.log("[WS] custom headers:", [x.split(":",1)[0] + ": <redacted>" if x.lower().startswith(("username:", "password:")) else x for x in header_lines])
                        self.bootstrap_after_connect()
                        if BOT_MASTER:
                            now = time.time()
                            reason = self._pending_reconnect_reason
                            self._pending_reconnect_reason = ""
                            should_notify = bool(reason and "1009" in reason) or (
                                now - self._last_connection_notice >= self._connection_notice_cooldown
                            )
                            if should_notify:
                                if reason:
                                    self.send_private_text(
                                        BOT_MASTER,
                                        "✅ عاد اتصال البوت بنجاح بعد انقطاع مؤقت. تم تقسيم الرسائل الكبيرة تلقائياً.",
                                    )
                                elif not self._had_connection:
                                    self.send_private_text(BOT_MASTER, "✅ تم الدخول والاتصال بنجاح.")
                                self._last_connection_notice = now
                        self._had_connection = True

                        while not self.stop_event.is_set():
                            try:
                                kind, message = self.ws.recv()
                            except socket.timeout:
                                # An idle room is normal. Do not reconnect just
                                # because no WebSocket frame arrived during the
                                # read timeout.
                                continue
                            if kind == "binary":
                                self.on_message(self.ws, message)
                            elif kind == "ping":
                                continue
                            elif kind == "pong":
                                continue
                            elif kind == "text":
                                self.log("[WS] unexpected text frame received")
                            elif kind == "close":
                                raise ConnectionError(f"WebSocket closed by server: {message}")
                        self._stop_heartbeat()
                        return
                    except Exception as e:
                        self._stop_heartbeat()
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
        print("=== Talkinchat Bot V22 - Talkin + YouTube Cookies + Giant Gift Cards ===", flush=True)
        missing = []
        if not BOT_ID:
            missing.append("BOT_ID (or BOT_USERNAME)")
        if not BOT_PWD:
            missing.append("BOT_PWD (or BOT_PASSWORD)")
        if not self.room and not MASTER_SERVICE_ENABLED:
            missing.append("GROUP_TO_JOIN (or FIRST_ROOM)")
        if missing:
            raise SystemExit(
                "Missing required deployment variables: " + ", ".join(missing) + ". "
                "Add them to Railway Variables (not the source code) and redeploy."
            )
        self.asset_server = start_asset_server()
        while not self.stop_event.is_set():
            try:
                self.run_once()
                # run_once normally blocks until stop_event or a socket error;
                # if it returns normally, the connection was not rejected.
                self._reconnect_delay = 10.0
            except Exception as e:
                self.last_error = str(e)
                if self._had_connection:
                    raw_reason = " ".join(str(e).split())
                    if "code': 1000" in raw_reason or '"code": 1000' in raw_reason:
                        raw_reason = "الخادم أغلق WebSocket إغلاقًا طبيعيًا (1000)"
                    if "1009" in raw_reason:
                        raw_reason = "الخادم أغلق WebSocket بسبب حجم الرسالة (1009)" + (f" | آخر غرفة: {self.room}" if self.room else "") + " | السبب التقني: " + raw_reason[:700]
                    elif self.room:
                        raw_reason = f"{raw_reason[:850]} | آخر غرفة: {self.room}"
                    self._pending_reconnect_reason = raw_reason[:1200]
                print("[BOT] error:", repr(e), flush=True)
            if not self.stop_event.is_set():
                delay = self._reconnect_delay
                print(f"[BOT] reconnecting in {int(delay)}s...", flush=True)
                if self.stop_event.wait(delay):
                    break
                self._reconnect_delay = min(self._reconnect_delay * 2.0, self._reconnect_delay_max)


if __name__ == "__main__":
    TalkinBot().start()
