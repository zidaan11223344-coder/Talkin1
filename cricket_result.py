"""Elegant cricket result-card renderer for the Talkin game."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("CRICKET_MEDIA_DIR", str(ROOT / "generated_games")))
FONT_CANDIDATES = (
    os.getenv("CRICKET_FONT", "").strip(),
    str(ROOT / "assets" / "NotoSansArabic-SemiBold.ttf"),
    str(ROOT / "assets" / "NotoSansArabic-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size: int):
    for candidate in FONT_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _latin_font(size: int):
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return _font(size)


def _has_arabic(value: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(value))


def _shape_rtl(value: str) -> str:
    text = str(value)
    if not _has_arabic(text) or arabic_reshaper is None or get_display is None:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _text(draw, xy, value, font, anchor="la", fill=(245, 247, 250), rtl=None):
    value = str(value)
    rtl = _has_arabic(value) if rtl is None else rtl
    try:
        draw.text(xy, value, font=font, fill=fill, anchor=anchor,
                  direction="rtl" if rtl else "ltr", language="ar" if rtl else None)
    except Exception:
        draw.text(xy, _shape_rtl(value) if rtl else value, font=font, fill=fill, anchor=anchor)


def _asset(name: str, size: tuple[int, int]) -> Image.Image | None:
    path = ROOT / "assets" / name
    if not path.is_file():
        return None
    try:
        image = Image.open(path).convert("RGBA")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        return image
    except Exception:
        return None


def _paste_cover(canvas, source: Image.Image | None, box, tint):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if source is None:
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(box, radius=26, fill=tint)
        return
    source = source.copy()
    source.thumbnail((w - 30, h - 30), Image.Resampling.LANCZOS)
    backdrop = Image.new("RGBA", (w, h), tint)
    backdrop.alpha_composite(source, ((w - source.width) // 2, (h - source.height) // 2))
    canvas.alpha_composite(backdrop, (x1, y1))


def render_result_image(*, match_id: str, team1_name: str = "الفريق الأول",
                        team1_players: Iterable[str] = (), team1_score: int = 0,
                        team2_name: str = "الفريق الثاني", team2_players: Iterable[str] = (),
                        team2_score: int = 0, player_scores: dict[str, int] | None = None,
                        player_awards: dict[str, int] | None = None, winner: str = "تعادل",
                        prize: int = 0, output_dir: str | Path | None = None,
                        players: Iterable[str] | None = None, human_score: int | None = None,
                        bot_score: int | None = None) -> str:
    """Render a cinematic two-team card; scores sit in high-contrast boxes above imagery."""
    target_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(ch for ch in str(match_id) if ch.isalnum())[:24] or "match"
    path = target_dir / f"cricket_result_{safe_id}.png"
    if players is not None:
        team1_players = players
    if human_score is not None:
        team1_score = human_score
    if bot_score is not None:
        team2_score = bot_score
    p1 = [str(p).lstrip("@") for p in team1_players if str(p).strip()]
    p2 = [str(p).lstrip("@") for p in team2_players if str(p).strip()]
    scores = {str(k).lstrip("@"): int(v) for k, v in (player_scores or {}).items()}
    awards = {str(k).lstrip("@"): int(v) for k, v in (player_awards or {}).items()}

    W, H = 1600, 960
    img = Image.new("RGBA", (W, H), (7, 13, 27, 255))
    bg = Image.new("RGBA", (W, H), (7, 13, 27, 255))
    bg = bg.filter(ImageFilter.GaussianBlur(1))
    img.alpha_composite(bg)
    draw = ImageDraw.Draw(img)
    gold, white = (247, 201, 92, 255), (245, 248, 252, 255)
    blue, red = (35, 157, 255, 255), (232, 62, 83, 255)
    draw.rounded_rectangle((24, 20, W - 24, H - 20), radius=34, fill=(16, 25, 43, 255), outline=(67, 91, 126, 255), width=3)
    _text(draw, (W // 2, 70), "نتيجة مباراة الكركيت", _font(58), anchor="mm", fill=gold, rtl=True)
    _text(draw, (W // 2, 132), f"الفائز: {winner}", _font(30), anchor="mm", fill=white, rtl=True)

    panels = [
        ((55, 190, W // 2 - 18, 875), str(team1_name), p1, int(team1_score), blue, "cricket_attack_blue.png"),
        ((W // 2 + 18, 190, W - 55, 875), str(team2_name), p2, int(team2_score), red, "cricket_defense_red.png"),
    ]
    for box, team_name, players_list, total, accent, hero in panels:
        draw.rounded_rectangle(box, radius=28, fill=(24, 35, 56, 255), outline=accent, width=5)
        _text(draw, ((box[0] + box[2]) // 2, box[1] + 42), team_name, _font(34), anchor="mm", fill=white, rtl=_has_arabic(team_name))
        # Number is deliberately placed in a bright box above the player image.
        score_box = (box[0] + 32, box[1] + 70, box[2] - 32, box[1] + 158)
        draw.rounded_rectangle(score_box, radius=18, fill=(8, 14, 27, 245), outline=accent, width=3)
        _text(draw, ((score_box[0] + score_box[2]) // 2, score_box[1] + 44), f"{total:,} نقطة", _latin_font(42), anchor="mm", fill=white, rtl=False)
        hero_box = (box[0] + 28, box[1] + 178, box[2] - 28, box[1] + 430)
        _paste_cover(img, _asset(hero, (hero_box[2] - hero_box[0], hero_box[3] - hero_box[1])), hero_box, (11, 24, 45, 255) if accent == blue else (45, 15, 29, 255))
        _text(draw, (box[0] + 38, box[1] + 462), "اللاعب", _font(23), anchor="la", fill=gold, rtl=True)
        _text(draw, (box[2] - 38, box[1] + 462), "النقاط / الجائزة", _font(23), anchor="ra", fill=gold, rtl=True)
        y = box[1] + 510
        for index, player in enumerate(players_list, 1):
            player = str(player).strip()
            value = int(scores.get(player, 0))
            award = int(awards.get(player, 0))
            draw.ellipse((box[0] + 35, y - 18, box[0] + 69, y + 16), fill=accent)
            _text(draw, (box[0] + 52, y - 1), str(index), _latin_font(18), anchor="mm", fill=white, rtl=False)
            _text(draw, (box[0] + 82, y), player, _font(25) if _has_arabic(player) else _latin_font(25), anchor="la", fill=white, rtl=_has_arabic(player))
            _text(draw, (box[2] - 38, y), f"{value} / {award:,}", _latin_font(22), anchor="ra", fill=white, rtl=False)
            y += 50
        if not players_list:
            _text(draw, ((box[0] + box[2]) // 2, y), "لا يوجد لاعبين", _font(23), anchor="mm", fill=white, rtl=True)
    if prize:
        draw.rounded_rectangle((W // 2 - 245, H - 70, W // 2 + 245, H - 30), radius=15, fill=(26, 84, 53, 255), outline=(107, 194, 132, 255), width=2)
        _text(draw, (W // 2, H - 50), f"الجائزة: {prize:,} نقطة", _font(22), anchor="mm", fill=white, rtl=True)
    img.convert("RGB").save(path, "PNG", optimize=True)
    return path.name
