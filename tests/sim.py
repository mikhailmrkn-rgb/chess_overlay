"""Draws fake chess boards / screens so the board reader can be tested without a real screen."""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import chess_overlay as co

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",          # Debian / Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",                   # Fedora
    "C:/Windows/Fonts/seguisym.ttf",                            # Windows (Segoe UI Symbol)
]
FONT = next((p for p in FONT_PATHS if os.path.exists(p)), None)
GLYPH = {"k": "\u265a", "q": "\u265b", "r": "\u265c", "b": "\u265d", "n": "\u265e", "p": "\u265f"}
GREEN = ((235, 236, 208), (115, 149, 82))     # Chess.com default
BROWN = ((240, 217, 181), (181, 136, 99))     # Lichess default

START = {}
for _f in range(8):
    START[8 + _f] = "P"
    START[48 + _f] = "p"
for _f, _p in enumerate("RNBQKBNR"):
    START[_f] = _p
    START[56 + _f] = _p.lower()

GAME = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1", "f8c5", "d2d4", "e5d4",
        "e4e5", "d7d5", "e5d6", "c5b4", "d6c7", "e8g8", "c7d8q", "f8d8"]  # castling, e.p., promotion


def to_grid(pos, white_bottom):
    g = ["."] * 64
    for sq, p in pos.items():
        r, c = co.sq_to_screen(sq, white_bottom)
        g[r * 8 + c] = p
    return "".join(g)


def board_list(pos):
    return [pos.get(i, ".") for i in range(64)]


def apply(pos, mv):
    pos = dict(pos)
    fr, to = co.name_sq(mv[:2]), co.name_sq(mv[2:4])
    p = pos.pop(fr)
    if p in "Kk" and abs(fr % 8 - to % 8) == 2:          # castling moves the rook too
        rank = fr // 8
        if to % 8 == 6:
            pos[rank * 8 + 5] = pos.pop(rank * 8 + 7)
        else:
            pos[rank * 8 + 3] = pos.pop(rank * 8 + 0)
    if p in "Pp" and fr % 8 != to % 8 and to not in pos:   # en passant
        pos.pop((fr // 8) * 8 + to % 8)
    if len(mv) > 4:
        p = mv[4].upper() if p.isupper() else mv[4]
    pos[to] = p
    return pos


def hl_idx(mv, white_bottom):
    out = []
    for nm in (mv[:2], mv[2:4]):
        r, c = co.sq_to_screen(co.name_sq(nm), white_bottom)
        out.append(r * 8 + c)
    return out


def piece_img(ch, s):
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, int(s * 0.82))
    fill, stroke = ((250, 250, 250, 255), (40, 40, 40, 255)) if ch.isupper() else \
                   ((86, 83, 82, 255), (30, 30, 30, 255))
    g = GLYPH[ch.lower()]
    bb = d.textbbox((0, 0), g, font=f, stroke_width=max(1, s // 40))
    x = (s - (bb[2] - bb[0])) / 2 - bb[0]
    y = (s - (bb[3] - bb[1])) / 2 - bb[1]
    d.text((x, y), g, font=f, fill=fill, stroke_width=max(1, s // 40), stroke_fill=stroke)
    return im


def render_board(grid, s, palette=GREEN, highlights=(), dots=(), labels=True, white_bottom=True,
                 gap=0, gap_color=(30, 30, 40), hl_color=(255, 255, 51), dark_first=False):
    light, dark = palette
    im = Image.new("RGB", (s * 8, s * 8), gap_color)
    d = ImageDraw.Draw(im)
    for r in range(8):
        for c in range(8):
            col = light if (r + c + dark_first) % 2 == 0 else dark
            if r * 8 + c in highlights:
                col = tuple(int(0.5 * v + 0.5 * h) for v, h in zip(col, hl_color))
            d.rectangle([c * s + gap, r * s + gap, (c + 1) * s - 1 - gap, (r + 1) * s - 1 - gap], fill=col)
    if labels:   # coordinates in the corners, like real sites
        lf = ImageFont.truetype(FONT, max(8, int(s * 0.16)))
        files = "abcdefgh" if white_bottom else "hgfedcba"
        ranks = "87654321" if white_bottom else "12345678"
        for r in range(8):
            d.text((3, r * s + 2), ranks[r], font=lf, fill=dark if r % 2 == 0 else light)
        for c in range(8):
            d.text(((c + 1) * s - int(s * 0.14), 8 * s - int(s * 0.2)), files[c], font=lf,
                   fill=light if c % 2 == 0 else dark)
    cache = {}
    for i, ch in enumerate(grid):
        if ch == ".":
            continue
        if ch not in cache:
            cache[ch] = piece_img(ch, s)
        im.paste(cache[ch], ((i % 8) * s, (i // 8) * s), cache[ch])
    for i in dots:   # "you can move here" hints
        cx, cy, rad = (i % 8) * s + s // 2, (i // 8) * s + s // 2, s // 6
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(0, 0, 0, 36))
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    return np.asarray(im)


def render_screen(board_img, W=1920, H=1080, x=600, y=140, noisy=False):
    scr = np.zeros((H, W, 3), np.uint8)
    scr[:] = (49, 46, 43)
    if noisy:   # a busy "3-D world" behind the game UI, as in a Roblox game
        rng = np.random.default_rng(1)
        yy, xx = np.mgrid[0:H, 0:W]
        scr[..., 0] = (90 + 60 * np.sin(xx / 97.0) + rng.integers(0, 30, (H, W))).clip(0, 255)
        scr[..., 1] = (120 + 50 * np.cos(yy / 71.0) + rng.integers(0, 30, (H, W))).clip(0, 255)
        scr[..., 2] = (140 + rng.integers(0, 40, (H, W))).clip(0, 255)
        scr[((xx // 37 + yy // 23) % 2).astype(bool) & (yy > 900)] = (200, 200, 200)
    scr[100:900, 1500:1880] = (38, 36, 33)     # sidebar, button, text-ish block
    scr[800:860, 1520:1860] = (129, 182, 76)
    scr[200:230, 1520:1700] = (200, 200, 200)
    h, w = board_img.shape[:2]
    scr[y:y + h, x:x + w] = board_img
    return scr


class FakeScreen:
    """Stands in for mss: grab() returns BGRA pixels from a numpy RGB screen."""
    monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]

    def __init__(self, screen=None):
        self.screen = screen

    def grab(self, reg):
        x, y = reg["left"] - self.monitors[0]["left"], reg["top"] - self.monitors[0]["top"]
        bgr = self.screen[y:y + reg["height"], x:x + reg["width"], ::-1]
        return np.dstack([bgr, np.full(bgr.shape[:2], 255, np.uint8)])
