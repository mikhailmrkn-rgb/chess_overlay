#!/usr/bin/env python3
"""
Chess Overlay - reads a chess board on your screen and draws the engine's best
move on top of it. Built for experimenting against computer bots.

  * Finds the board automatically - Chess.com, Lichess, RoChess on Roblox or any
    flat 2-D board in any colours - or you drag a box around it ("Select board").
  * Learns what your piece set looks like from a starting position (one time,
    saved as pieces_*.npz next to this file, one per board style).
  * Asks Stockfish for the best moves (top 3, adjustable strength) and draws
    click-through arrows and an eval bar on top of the board. That window is
    hidden from screenshots, so it never confuses the board reader.
  * Logs every suggestion and what you actually played to experiment_log.csv.

Needs Windows 10 (version 2004 or newer) or Windows 11. Run it from Python 3.9+
with numpy + mss ("Start Chess Overlay.bat"), or build "Chess Overlay.exe" with
"Build EXE.bat". Either way it downloads Stockfish by itself on first run.
"""

import ctypes
import json
import math
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import zipfile

import numpy as np

IS_WINDOWS = sys.platform == "win32"
FROZEN = bool(getattr(sys, "frozen", False))       # running as "Chess Overlay.exe"
# where the .exe / .py lives, and where bundled read-only files (the icon) are
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)


def _data_dir():
    """Where settings, learned pieces, logs and the engine go. The .exe keeps them in
    %APPDATA%\\Chess Overlay so it doesn't litter the folder it's in (e.g. Desktop)."""
    if FROZEN:
        base = os.environ.get("APPDATA") if IS_WINDOWS else None
        d = os.path.join(base or os.path.join(os.path.expanduser("~"), ".local", "share"), "Chess Overlay")
    else:
        d = APP_DIR
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


DATA_DIR = _data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "chess_overlay.log")
ENGINE_DIR = os.path.join(DATA_DIR, "stockfish")
STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/latest/download/"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Board square colours (light, dark) to look for on screen.
KNOWN_PALETTES = [
    ((235, 236, 208), (115, 149, 82)),   # Chess.com "Green" (default)
    ((238, 238, 210), (118, 150, 86)),   # Chess.com "Green" (older shade)
    ((237, 214, 176), (184, 135, 98)),   # Chess.com "Brown"
    ((240, 217, 181), (181, 136, 99)),   # Lichess "Brown"
    ((222, 227, 230), (140, 162, 173)),  # Lichess "Blue"
]

BG_TOL = 40         # max |dR|+|dG|+|dB| for a pixel to count as a square colour
MASK_T = 45         # min difference from the square background to count as "piece"
EMPTY_FRAC = 0.035  # squares with a smaller share of piece pixels are empty
FEAT = 16           # pieces are compared as FEAT x FEAT thumbnails
MIN_BOARD = 160     # smallest board (px) we look for
PATTERN_MIN = 44    # squares (of 64) that must show the expected light/dark colour
BOOK_VERSION = 3    # bump when the piece thumbnails change format
ANY_STYLE_EVERY = 4.0  # seconds between (slower) searches for boards in unknown colours

PIECE_NAMES = {"p": "Pawn", "n": "Knight", "b": "Bishop", "r": "Rook", "q": "Queen", "k": "King"}
FILES = "abcdefgh"
YOUR_COLOR = "#FF9F1C"   # arrow colour for your moves
BOT_COLOR = "#3D9BFF"    # arrow colour for the bot's moves (optional)


def log(msg):
    line = time.strftime("%H:%M:%S ") + str(msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# =============================================================================
#  Vision: finding the board and reading squares
# =============================================================================

def color_dist(img, color):
    """Per-pixel |dR|+|dG|+|dB| between an image and one colour."""
    return np.abs(img.astype(np.int16) - np.asarray(color, np.int16)).sum(axis=-1)


def runs(flags, max_gap=0):
    """(start, end) pairs of consecutive True values in a 1-D array. Gaps of up to
    max_gap False values are bridged (some boards draw thin lines between squares)."""
    a = np.concatenate(([0], np.asarray(flags, np.int8), [0]))
    d = np.diff(a)
    out = []
    for st, en in zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()):
        if out and st - out[-1][1] <= max_gap:
            out[-1] = (out[-1][0], en)
        else:
            out.append((st, en))
    return out


def block_mean(a, n):
    """Shrink a 2-D array to n x n by averaging blocks."""
    h, w = a.shape
    ys = np.linspace(0, h, n + 1).astype(int)
    xs = np.linspace(0, w, n + 1).astype(int)
    t = np.add.reduceat(a, ys[:-1], axis=0)
    t = np.add.reduceat(t, xs[:-1], axis=1)
    return t / np.outer(np.diff(ys), np.diff(xs))


def square_edges(size):
    s = size / 8.0
    return [int(round(i * s)) for i in range(9)]


def ring_bg(sq):
    """Background colour of a square: median of a thin band just inside its edge."""
    h, w = sq.shape[:2]
    a = max(1, int(h * 0.03))
    b = max(a + 2, int(h * 0.10))
    parts = (sq[a:b, a:w - a], sq[h - b:h - a, a:w - a], sq[b:h - b, a:b], sq[b:h - b, w - b:w - a])
    px = np.concatenate([p.reshape(-1, 3) for p in parts])
    return np.median(px, axis=0)


def bg_class(bg, light, dark):
    dl = float(np.abs(bg - light).sum())
    dd = float(np.abs(bg - dark).sum())
    if dl <= BG_TOL and dl <= dd:
        return "L"
    if dd <= BG_TOL:
        return "D"
    return "H"  # highlighted (last move / selection) or something covering it


class SquareInfo:
    __slots__ = ("bg", "cls", "frac", "feat", "lum")


def fill_holes(m):
    """Fill the inside of outlines in a small boolean image (anything the border can't reach)."""
    free = ~m
    outside = np.zeros_like(m)
    outside[0, :], outside[-1, :] = free[0, :], free[-1, :]
    outside[:, 0], outside[:, -1] = free[:, 0], free[:, -1]
    while True:
        grown = outside.copy()
        grown[1:, :] |= outside[:-1, :]
        grown[:-1, :] |= outside[1:, :]
        grown[:, 1:] |= outside[:, :-1]
        grown[:, :-1] |= outside[:, 1:]
        grown &= free
        if np.array_equal(grown, outside):
            return ~outside
        outside = grown


def analyze_square(sq, light, dark):
    h, w = sq.shape[:2]
    info = SquareInfo()
    bg = ring_bg(sq)
    info.bg = bg
    info.cls = bg_class(bg, light, dark)
    info.feat = None
    info.lum = None
    mask = np.abs(sq.astype(np.int16) - bg.astype(np.int16)).sum(axis=2) > MASK_T
    k = int(h * 0.22)                 # ignore the corners, where boards print coordinates
    mask[:k, :k] = False
    mask[:k, w - k:] = False
    mask[h - k:, :k] = False
    mask[h - k:, w - k:] = False
    m = max(1, int(h * 0.08))         # stay clear of square edges / grid lines
    inner = mask[m:h - m, m:w - m]
    raw = float(inner.mean())
    if raw < EMPTY_FRAC * 0.4:
        info.frac = raw
        return info
    # Piece silhouette = outline + everything inside it. Filling the inside matters
    # when a piece's colour is close to the square's colour (white piece on a pale square).
    n = 2 * FEAT if min(inner.shape) >= 2 * FEAT else FEAT
    sil = fill_holes(block_mean(inner.astype(np.float64), n) > 0.12)
    info.frac = float(sil.mean())
    if info.frac >= EMPTY_FRAC:
        lum = block_mean((sq[m:h - m, m:w - m] @ np.array([0.299, 0.587, 0.114])) / 255.0, n)
        silf = sil.astype(np.float64)
        info.feat = np.concatenate([block_mean(silf, FEAT).ravel(),
                                    block_mean(lum * silf, FEAT).ravel()]).astype(np.float32)
        info.lum = float(lum[sil].mean())
    return info


def analyze_board(img, light, dark):
    """img: RGB array of exactly the board. Returns 64 SquareInfo in screen order
    (row 0 = top of the screen, column 0 = left)."""
    light = np.asarray(light, np.float64)
    dark = np.asarray(dark, np.float64)
    e = square_edges(min(img.shape[0], img.shape[1]))
    return [analyze_square(img[e[r]:e[r + 1], e[c]:e[c + 1]], light, dark)
            for r in range(8) for c in range(8)]


def square_classes(img, light, dark):
    light = np.asarray(light, np.float64)
    dark = np.asarray(dark, np.float64)
    e = square_edges(min(img.shape[0], img.shape[1]))
    return [bg_class(ring_bg(img[e[r]:e[r + 1], e[c]:e[c + 1]]), light, dark)
            for r in range(8) for c in range(8)]


def board_check(classes, parity):
    """(good, bad): squares showing the expected colour / the opposite colour.
    parity 0 = top-left square is light (real chess boards), 1 = top-left is dark."""
    good = bad = 0
    for i, cls in enumerate(classes):
        expected = "L" if ((i // 8) + (i % 8) + parity) % 2 == 0 else "D"
        if cls == expected:
            good += 1
        elif cls != "H":
            bad += 1
    return good, bad


def board_parity(img, light, dark, need=PATTERN_MIN):
    """Parity (0/1) if img looks like a chess board in these colours, else None."""
    classes = square_classes(img, light, dark)
    for parity in (0, 1):
        good, bad = board_check(classes, parity)
        if good >= need and bad <= 4:
            return parity
    return None


def color_pairs(img, n_colors=8, min_count=0):
    """Pairs of the most common flat colours in img, as (light, dark) int tuples."""
    q = (img >> 3).astype(np.int32)
    keys = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    vals, counts = np.unique(keys.ravel(), return_counts=True)
    colors = []
    for i in np.argsort(-counts)[:n_colors]:
        if counts[i] < min_count:
            break
        colors.append((img[keys == vals[i]].reshape(-1, 3).mean(axis=0), int(counts[i])))
    lum = np.array([0.299, 0.587, 0.114])
    pairs = []
    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            a, b = colors[i][0], colors[j][0]
            if np.abs(a - b).sum() >= 40:
                light, dark = (a, b) if a @ lum >= b @ lum else (b, a)
                pairs.append((colors[i][1] + colors[j][1],
                              tuple(int(v) for v in np.round(light)),
                              tuple(int(v) for v in np.round(dark))))
    pairs.sort(key=lambda p: -p[0])
    return [(l, d) for _, l, d in pairs]


def any_board_palettes(screen):
    """Colour pairs worth trying when the board style is unknown (e.g. RoChess themes)."""
    small = screen[::4, ::4]
    return color_pairs(small, n_colors=10, min_count=int((MIN_BOARD / 4) ** 2 * 0.15))


def _best_run(flags, lo, hi, max_gap=0):
    """The run of True values that overlaps [lo, hi) the most."""
    best, best_ov = None, 0
    for a, b in runs(flags, max_gap):
        ov = min(b, hi) - max(a, lo)
        if ov > best_ov:
            best, best_ov = (a, b), ov
    return best


def locate_squares(ml, md, min_size, max_gap=6):
    """Find square areas where BOTH square colours show up row after row and column
    after column - that is what a board looks like, and a background that merely
    happens to share one of the colours does not. Returns [(x, y, size)]."""
    def both(a, b, n):
        return (a >= n) & (b >= n)

    found = []
    for r0, r1 in runs(both(ml.sum(axis=1), md.sum(axis=1), min_size * 0.08), max_gap):
        if r1 - r0 < min_size:
            continue
        for c0, c1 in runs(both(ml[r0:r1].sum(axis=0), md[r0:r1].sum(axis=0), (r1 - r0) * 0.06), max_gap):
            if c1 - c0 < min_size:
                continue
            y0, y1, x0, x1 = r0, r1, c0, c1
            for _ in range(4):  # tighten rows/cols against each other
                n = (x1 - x0) * 0.06
                rr = _best_run(both(ml[:, x0:x1].sum(axis=1), md[:, x0:x1].sum(axis=1), n), y0, y1, max_gap)
                if rr is None:
                    break
                y0, y1 = rr
                n = (y1 - y0) * 0.06
                cc = _best_run(both(ml[y0:y1].sum(axis=0), md[y0:y1].sum(axis=0), n), x0, x1, max_gap)
                if cc is None:
                    break
                x0, x1 = cc
            w, h = x1 - x0, y1 - y0
            if w >= min_size and abs(w - h) <= max(4, 0.04 * w):
                found.append((x0, y0, int(round((w + h) / 2))))
    return found


def color_masks(img, light, dark):
    return color_dist(img, light) <= BG_TOL, color_dist(img, dark) <= BG_TOL


def snap_grid(img, x, y, size, light, dark):
    """Some boards (common in Roblox games) draw thin lines between squares. Then the
    coloured area is one line-width short of 8 equal cells: widen the box by that much
    so every eighth of it is centred on a square."""
    board = img[y:y + size, x:x + size]
    m = (color_dist(board, light) <= BG_TOL) | (color_dist(board, dark) <= BG_TOL)
    edge = max(2, size // 50)
    widths = [float((prof[edge:size - edge] < 0.05).sum()) / 7.0
              for prof in (m.mean(axis=0), m.mean(axis=1))]
    gap = int(round(sum(widths) / 2))
    if gap < 1 or abs(widths[0] - widths[1]) > 1.5 or gap > size / 8 * 0.25:
        return x, y, size
    nx, ny = x - gap // 2, y - gap // 2
    if nx < 0 or ny < 0 or nx + size + gap > img.shape[1] or ny + size + gap > img.shape[0]:
        return x, y, size
    return nx, ny, size + gap


def find_board(img, palettes, min_size=MIN_BOARD):
    """Search a screenshot for a chess board. Returns dict(x, y, size, light, dark) or None."""
    small = img[::2, ::2]
    best = None
    for light, dark in palettes:
        ml, md = color_masks(small, light, dark)
        if ml.sum() < (min_size / 2) ** 2 * 0.08 or md.sum() < (min_size / 2) ** 2 * 0.08:
            continue
        for sx, sy, ssize in locate_squares(ml, md, min_size // 2, max_gap=3):
            # refine at full resolution around the coarse hit
            pad = 6
            x0, y0 = max(0, sx * 2 - pad), max(0, sy * 2 - pad)
            x1 = min(img.shape[1], sx * 2 + ssize * 2 + pad)
            y1 = min(img.shape[0], sy * 2 + ssize * 2 + pad)
            sub = img[y0:y1, x0:x1]
            for fx, fy, size in locate_squares(*color_masks(sub, light, dark), min_size):
                x, y = x0 + fx, y0 + fy
                board = img[y:y + size, x:x + size]
                if board.shape[0] < size or board.shape[1] < size:
                    continue
                parity = board_parity(board, light, dark, PATTERN_MIN + 4)
                if parity is not None:
                    x, y, size = snap_grid(img, x, y, size, light, dark)
                if parity is not None and (best is None or size > best["size"]):
                    best = dict(x=x, y=y, size=size, parity=parity,
                                light=tuple(int(round(v)) for v in light),
                                dark=tuple(int(round(v)) for v in dark))
        if best is not None:
            break
    return best


def board_from_selection(img, rect):
    """The user dragged a box roughly around a board. Learn its two square colours
    and snap to the exact board edges. Returns dict like find_board, or None."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = rect
    x0, x1 = sorted((max(0, int(x0)), min(W, int(x1))))
    y0, y1 = sorted((max(0, int(y0)), min(H, int(y1))))
    if x1 - x0 < 64 or y1 - y0 < 64:
        return None
    pairs = color_pairs(img[y0:y1, x0:x1], n_colors=5)
    pad = int(0.12 * max(x1 - x0, y1 - y0))
    rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
    rx1, ry1 = min(W, x1 + pad), min(H, y1 + pad)
    region = img[ry0:ry1, rx0:rx1]
    min_size = int(min(x1 - x0, y1 - y0) * 0.6)
    for light, dark in pairs:
        cands = sorted(locate_squares(*color_masks(region, light, dark), max(64, min_size)),
                       key=lambda t: -t[2])
        for fx, fy, size in cands:
            x, y = rx0 + fx, ry0 + fy
            board = img[y:y + size, x:x + size]
            if board.shape[0] != size or board.shape[1] != size:
                continue
            parity = board_parity(board, light, dark)
            if parity is not None:
                x, y, size = snap_grid(img, x, y, size, light, dark)
                return dict(x=x, y=y, size=size, parity=parity, light=light, dark=dark)
    return None


# =============================================================================
#  Pieces: learn from a starting position, then recognise
# =============================================================================

def start_grid(white_bottom):
    """Starting position as 64 chars in screen order ('.' = empty, upper = white)."""
    g = "rnbqkbnr" + "p" * 8 + "." * 32 + "P" * 8 + "RNBQKBNR"
    return g if white_bottom else g[::-1]


def occupancy(infos):
    return [i.frac >= EMPTY_FRAC for i in infos]


def is_start_occupancy(infos):
    occ = occupancy(infos)
    return all(occ[i] == (i < 16 or i >= 48) for i in range(64))


class PieceBook:
    """Thumbnails of every piece, learnt from a starting position. It keeps adding
    clear-cut examples it sees during play (a queen on the other square colour, a
    piece on a highlighted square...), so recognition gets steadier over time."""

    MAX_PER_PIECE = 16

    def __init__(self, feats, labels, threshold):
        self.feats = np.asarray(feats, np.float32)
        self.labels = list(labels)
        self.lab = np.array(self.labels)
        self.threshold = float(threshold)

    @classmethod
    def learn(cls, infos):
        top = np.mean([infos[i].lum for i in range(16)])
        bottom = np.mean([infos[i].lum for i in range(48, 64)])
        grid = start_grid(white_bottom=bottom > top)
        idx = [i for i in range(64) if grid[i] != "."]
        feats = np.stack([infos[i].feat for i in idx])
        labels = [grid[i] for i in idx]
        # How far apart are different kinds of piece? Anything much further than
        # that from every known piece is "not a piece I know" (a dot, an arrow...).
        d = ((feats[:, None, :] - feats[None, :, :]) ** 2).mean(axis=2)
        lab = np.array(labels)
        other = np.where(lab[:, None] != lab[None, :], d, np.inf)
        threshold = 0.6 * float(np.median(other.min(axis=1)))
        return cls(feats, labels, threshold)

    def classify(self, infos, details=False):
        """64-char grid, or None if any occupied square is not recognised.
        With details=True also returns, per square, (distance to best match,
        distance to the nearest *different* piece)."""
        out, det = [], []
        for info in infos:
            if info.feat is None:
                out.append(".")
                det.append(None)
                continue
            d = ((self.feats - info.feat) ** 2).mean(axis=1)
            j = int(np.argmin(d))
            if d[j] > self.threshold:
                return (None, None) if details else None
            label = self.labels[j]
            out.append(label)
            if details:
                rest = d[self.lab != label]
                det.append((float(d[j]), float(rest.min()) if rest.size else np.inf))
        grid = "".join(out)
        return (grid, det) if details else grid

    def adapt(self, infos, grid, det):
        """Remember pieces that were recognised for sure but looked a bit different
        from anything stored. Returns how many were added."""
        added = 0
        for info, label, dd in zip(infos, grid, det):
            if dd is None:
                continue
            best, other = dd
            if 0.3 * self.threshold < best and best * 3 < other and \
                    int((self.lab == label).sum()) < self.MAX_PER_PIECE:
                self.feats = np.vstack([self.feats, info.feat[None, :]])
                self.labels.append(label)
                self.lab = np.array(self.labels)
                added += 1
        return added

    def save(self, path):
        np.savez(path, feats=self.feats, labels=np.array(self.labels),
                 threshold=np.array([self.threshold]), feat=np.array([FEAT]),
                 ver=np.array([BOOK_VERSION]))

    @classmethod
    def load(cls, path):
        try:
            z = np.load(path)
            if int(z["feat"][0]) != FEAT or "ver" not in z or int(z["ver"][0]) != BOOK_VERSION:
                return None
            return cls(z["feats"], [str(s) for s in z["labels"]], float(z["threshold"][0]))
        except Exception:
            return None


# =============================================================================
#  Chess logic: board squares, legality checks, FEN, whose turn
# =============================================================================

def screen_to_sq(r, c, white_bottom):
    """Screen row/col -> square index (a1 = 0, h8 = 63)."""
    return (7 - r) * 8 + c if white_bottom else r * 8 + (7 - c)


def sq_to_screen(sq, white_bottom):
    f, rk = sq % 8, sq // 8
    return (7 - rk, f) if white_bottom else (rk, 7 - f)


def sq_name(sq):
    return FILES[sq % 8] + str(sq // 8 + 1)


def name_sq(name):
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def grid_to_board(grid, white_bottom):
    board = ["."] * 64
    for i, ch in enumerate(grid):
        board[screen_to_sq(i // 8, i % 8, white_bottom)] = ch
    return board


KNIGHT_STEPS = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
KING_STEPS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def is_attacked(board, sq, by_white):
    f, r = sq % 8, sq // 8

    def at(ff, rr):
        return board[rr * 8 + ff] if 0 <= ff < 8 and 0 <= rr < 8 else None

    P, N, B, R, Q, K = "PNBRQK" if by_white else "pnbrqk"
    pr = r - 1 if by_white else r + 1
    if at(f - 1, pr) == P or at(f + 1, pr) == P:
        return True
    if any(at(f + df, r + dr) == N for df, dr in KNIGHT_STEPS):
        return True
    if any(at(f + df, r + dr) == K for df, dr in KING_STEPS):
        return True
    for (df, dr), sliders in (((1, 0), (R, Q)), ((-1, 0), (R, Q)), ((0, 1), (R, Q)), ((0, -1), (R, Q)),
                              ((1, 1), (B, Q)), ((1, -1), (B, Q)), ((-1, 1), (B, Q)), ((-1, -1), (B, Q))):
        ff, rr = f + df, r + dr
        while 0 <= ff < 8 and 0 <= rr < 8:
            p = board[rr * 8 + ff]
            if p != ".":
                if p in sliders:
                    return True
                break
            ff, rr = ff + df, rr + dr
    return False


def position_problem(board, turn):
    """None if the position is playable, else a short reason."""
    if board.count("K") != 1 or board.count("k") != 1:
        return "kings"
    if any(board[i] in "Pp" for i in list(range(8)) + list(range(56, 64))):
        return "pawns"
    if sum(ch.isupper() for ch in board) > 16 or sum(ch.islower() for ch in board) > 16:
        return "too many pieces"
    # the side that just moved can't be left in check
    other_king = board.index("k" if turn == "w" else "K")
    if is_attacked(board, other_king, by_white=(turn == "w")):
        return "check"
    return None


def make_fen(board, turn, castling, ep):
    rows = []
    for rk in range(7, -1, -1):
        s, empty = "", 0
        for f in range(8):
            ch = board[rk * 8 + f]
            if ch == ".":
                empty += 1
            else:
                if empty:
                    s += str(empty)
                    empty = 0
                s += ch
        rows.append(s + (str(empty) if empty else ""))
    return "%s %s %s %s 0 1" % ("/".join(rows), turn, castling or "-", ep or "-")


def infer_move(before, after, white):
    """The move one side made between two boards (a1 = 0 lists) in UCI form, or None
    if it can't be told for sure. Works even if the other side has moved since."""
    own = str.isupper if white else str.islower
    gone = [i for i in range(64) if own(before[i]) and after[i] != before[i]]
    came = [i for i in range(64) if own(after[i]) and before[i] != after[i]]
    king = "K" if white else "k"
    kf = [i for i in gone if before[i] == king]
    kt = [i for i in came if after[i] == king]
    if kf and kt:                                   # king moves, castling included
        return sq_name(kf[0]) + sq_name(kt[0])
    if len(came) != 1:
        return None
    to = came[0]
    piece = after[to]
    cands = [i for i in gone if before[i] == piece]
    promo = ""
    if not cands and piece.lower() != "p" and to // 8 in (0, 7):
        cands = [i for i in gone if before[i].lower() == "p"]
        promo = piece.lower()
    if len(cands) != 1:
        return None
    return sq_name(cands[0]) + sq_name(to) + promo


def white_pov(score, turn):
    """Engine score (side to move's view) -> White's view."""
    if score is None or turn == "w":
        return score
    return (score[0], -score[1])


def guess_white_bottom(grid):
    """Mid-game guess: white's pawns and king usually sit nearer to the bottom
    of the screen when you play white."""
    rw = [i // 8 for i, ch in enumerate(grid) if ch in "PK"]
    rb = [i // 8 for i, ch in enumerate(grid) if ch in "pk"]
    if not rw or not rb:
        return True
    return float(np.mean(rw)) >= float(np.mean(rb))


class GameTracker:
    """Turns a sequence of recognised grids into FEN positions."""

    def __init__(self):
        self.game_id = 0
        self.reset()

    def reset(self):
        self.prev = None
        self.white_bottom = None
        self.lost = set()
        self.turn = None
        self.how = None
        self.last_move = None

    def flip(self):
        if self.white_bottom is not None:
            self.white_bottom = not self.white_bottom
            self.lost = set()

    def update(self, grid, infos):
        prev = self.prev
        same = prev == grid
        start_wb, start_bb = grid == start_grid(True), grid == start_grid(False)
        count = sum(ch != "." for ch in grid)
        new_game = prev is None or (not same and (start_wb or start_bb or
                                                  count > sum(ch != "." for ch in prev)))
        if new_game:
            self.game_id += 1
            self.lost = set()
            self.white_bottom = None
            self.turn = None

        # --- which way round is the board? ---
        if start_wb or start_bb:
            if self.white_bottom is None or new_game:
                self.white_bottom = start_wb
        if self.white_bottom is None:
            self.white_bottom = guess_white_bottom(grid)
        wb = self.white_bottom

        # --- whose turn is it? ---
        if not same or self.turn is None:
            turn, how, last_move = None, None, None
            hl = [i for i, inf in enumerate(infos) if inf.cls == "H"]
            occ = [i for i in hl if grid[i] != "."]
            emp = [i for i in hl if grid[i] == "."]
            if len(hl) == 2 and len(occ) == 1:          # last-move highlight (any colour)
                turn = "b" if grid[occ[0]].isupper() else "w"
                how, last_move = "highlight", (emp[0], occ[0])
            if turn is None and prev is not None and not new_game and not same:
                arrived = {grid[i].isupper() for i in range(64) if grid[i] != "." and grid[i] != prev[i]}
                if len(arrived) == 1:
                    turn, how = ("b" if arrived.pop() else "w"), "diff"
            if turn is None and (start_wb or start_bb):
                turn, how = "w", "start"
            if turn is None:
                turn, how = ("w" if wb else "b"), "guess"   # assume it's your move
            self.turn, self.how, self.last_move = turn, how, last_move

        board = grid_to_board(grid, wb)

        # --- castling rights: lost forever once king/rook leave home ---
        if board[4] != "K":
            self.lost |= {"K", "Q"}
        if board[7] != "R":
            self.lost.add("K")
        if board[0] != "R":
            self.lost.add("Q")
        if board[60] != "k":
            self.lost |= {"k", "q"}
        if board[63] != "r":
            self.lost.add("k")
        if board[56] != "r":
            self.lost.add("q")
        castling = "".join(x for x in "KQkq" if x not in self.lost)

        # --- en passant (from the last-move highlight) ---
        ep = None
        if self.last_move:
            fr = screen_to_sq(self.last_move[0] // 8, self.last_move[0] % 8, wb)
            to = screen_to_sq(self.last_move[1] // 8, self.last_move[1] % 8, wb)
            if board[to] in "Pp" and fr % 8 == to % 8 and abs(fr // 8 - to // 8) == 2:
                ep = sq_name((fr + to) // 2)

        turn = self.turn
        problem = position_problem(board, turn)
        if problem == "check" and self.how in ("guess", "diff"):
            turn = "b" if turn == "w" else "w"
            problem = position_problem(board, turn)
            if problem is None:
                self.turn = turn
                ep = None
        self.prev = grid
        if problem:
            return dict(error=problem, white_bottom=wb)
        return dict(fen=make_fen(board, turn, castling, ep), turn=turn, how=self.how,
                    white_bottom=wb, board=board)


# =============================================================================
#  Stockfish (UCI)
# =============================================================================

# Safest-first order for engine builds we didn't test ourselves.
ENGINE_PREFERENCE = ["universal", "avx2", "bmi2", "sse41", "ssse3", "x86-64", "arm", "avx512", "vnni"]


def engine_rank(path):
    name = os.path.basename(path).lower()
    for i, key in enumerate(ENGINE_PREFERENCE):
        if key in name:
            return (i, len(name))
    return (len(ENGINE_PREFERENCE), len(name))


def stockfish_candidates(root, depth=3):
    found = []
    if not os.path.isdir(root):
        return found
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(("_", "."))]
        if here[len(root):].count(os.sep) >= depth:
            dirs[:] = []
        for f in files:
            low = f.lower()
            if low.startswith("stockfish") and (low.endswith(".exe") if IS_WINDOWS else "." not in low):
                found.append(os.path.join(here, f))
    return sorted(found, key=engine_rank)


def find_stockfish():
    try:  # the build we downloaded and tested ourselves
        with open(os.path.join(ENGINE_DIR, "engine.txt"), encoding="utf-8") as f:
            path = os.path.join(ENGINE_DIR, f.read().strip())
        if os.path.isfile(path):
            return path
    except OSError:
        pass
    for root, depth in ((ENGINE_DIR, 3), (DATA_DIR, 1), (APP_DIR, 1 if FROZEN else 3)):
        found = stockfish_candidates(root, depth)
        if found:
            return found[0]
    return shutil.which("stockfish")


def engine_works(path):
    """Start an engine and let it think for a moment - catches builds this CPU can't run."""
    try:
        engine = Engine(path)
    except Exception:
        return False
    try:
        move, _ = engine.best_move(START_FEN, 0.3)
        return move is not None
    except Exception:
        return False
    finally:
        engine.close()


def stockfish_zip_names():
    arch = (os.environ.get("PROCESSOR_ARCHITECTURE", "") + " " + platform.machine()).upper()
    x64 = ["stockfish-windows-x86-64-universal.zip", "stockfish-windows-x86-64-avx2.zip",
           "stockfish-windows-x86-64.zip"]
    return (["stockfish-windows-arm64-universal.zip"] + x64) if "ARM" in arch else x64


def download_stockfish(progress):
    """Download Stockfish from its official GitHub releases into ENGINE_DIR and return the
    path of a build that runs on this computer. progress(text) reports what's happening."""
    work = os.path.join(ENGINE_DIR, "_download")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    zpath = os.path.join(work, "stockfish.zip")
    errors = []
    try:
        for name in stockfish_zip_names():
            try:
                req = urllib.request.Request(STOCKFISH_URL + name, headers={"User-Agent": "ChessOverlay"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(zpath, "wb") as out:
                    total = int(resp.headers.get("Content-Length") or 0)
                    done, shown = 0, -1
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        pct = int(100 * done / total) if total else -1
                        if pct != shown:
                            shown = pct
                            progress("Downloading the Stockfish chess engine (one time)… %s"
                                     % (("%d%%" % pct) if pct >= 0 else "%d MB" % (done >> 20)))
                break
            except Exception as e:
                errors.append("%s: %s" % (name, e))
                log("Download failed: %s: %s" % (name, e))
        else:
            raise RuntimeError("; ".join(errors) or "download failed")

        progress("Unpacking Stockfish…")
        unpacked = os.path.join(work, "unpacked")
        with zipfile.ZipFile(zpath) as z:
            z.extractall(unpacked)
        candidates = stockfish_candidates(unpacked, depth=6)
        if not candidates:
            raise RuntimeError("no engine inside the download")
        for cand in candidates:
            if not IS_WINDOWS:
                os.chmod(cand, 0o755)
            progress("Checking Stockfish works on this PC…")
            if engine_works(cand):
                folder = os.path.dirname(cand)
                for f in os.listdir(folder):     # the build plus anything next to it (licence…)
                    src = os.path.join(folder, f)
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(ENGINE_DIR, f))
                with open(os.path.join(ENGINE_DIR, "engine.txt"), "w", encoding="utf-8") as f:
                    f.write(os.path.basename(cand))
                return os.path.join(ENGINE_DIR, os.path.basename(cand))
            log("Engine build doesn't run here: " + os.path.basename(cand))
        raise RuntimeError("none of the downloaded builds run on this PC")
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Engine:
    def __init__(self, path):
        path = os.path.abspath(path)
        flags = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, universal_newlines=True, bufsize=1,
                                     cwd=os.path.dirname(path) or None, creationflags=flags)
        self.lines = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        self.send("uci")
        self.wait_for("uciok", 15)
        threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        self.send("setoption name Threads value %d" % threads)
        self.send("setoption name Hash value 64")
        self.send("isready")
        self.wait_for("readyok", 15)

    def _reader(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line.strip())
        finally:
            self.lines.put(None)

    def send(self, cmd):
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _get(self, deadline):
        try:
            line = self.lines.get(timeout=max(0.05, deadline - time.time()))
        except queue.Empty:
            raise TimeoutError("engine did not answer")
        if line is None:
            raise RuntimeError("engine stopped")
        return line

    def wait_for(self, prefix, timeout):
        deadline = time.time() + timeout
        while True:
            line = self._get(deadline)
            if line.startswith(prefix):
                return line

    def configure(self, multipv=1, elo=0):
        """multipv: how many candidate moves to report. elo: 0 = full strength,
        otherwise Stockfish plays like a player of about that rating."""
        if getattr(self, "_config", None) == (multipv, elo):
            return
        self.send("setoption name MultiPV value %d" % multipv)
        if elo:
            self.send("setoption name UCI_LimitStrength value true")
            self.send("setoption name UCI_Elo value %d" % elo)
        else:
            self.send("setoption name UCI_LimitStrength value false")
        self.send("isready")
        self.wait_for("readyok", 10)
        self._config = (multipv, elo)

    def analyse(self, fen, seconds):
        """Returns (bestmove, lines): lines = [(move, score, pv)], best first.
        score is ("cp", centipawns) or ("mate", n), from the side to move's view."""
        while not self.lines.empty():
            if self.lines.get_nowait() is None:
                raise RuntimeError("engine stopped")
        self.send("position fen " + fen)
        self.send("go movetime %d" % max(50, int(seconds * 1000)))
        deadline = time.time() + seconds + 15
        found = {}
        while True:
            line = self._get(deadline)
            if line.startswith("info") and " score " in line and " pv " in line:
                t = line.split()
                try:
                    k = int(t[t.index("multipv") + 1]) if "multipv" in t else 1
                    i = t.index("score")
                    pv = t[t.index("pv") + 1:]
                    found[k] = (pv[0], (t[i + 1], int(t[i + 2])), pv)
                except (IndexError, ValueError):
                    pass
            elif line.startswith("bestmove"):
                t = line.split()
                mv = t[1] if len(t) > 1 else None
                mv = None if mv in (None, "(none)", "0000") else mv
                return mv, [found[k] for k in sorted(found)]

    def best_move(self, fen, seconds):
        mv, lines = self.analyse(fen, seconds)
        score = next((sc for m, sc, _ in lines if m == mv), lines[0][1] if lines else None)
        return mv, score

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            self.proc.stdin.close()
        except Exception:
            pass


def format_score(score):
    if score is None:
        return ""
    kind, v = score
    if kind == "mate":
        return "mate in %d" % v if v > 0 else "gets mated in %d" % -v
    return "%+.2f" % (v / 100.0)


def short_move(board, mv):
    fr, to = name_sq(mv[:2]), name_sq(mv[2:4])
    p = board[fr].upper()
    if p == "K" and abs(fr % 8 - to % 8) == 2:
        return "O-O" if to % 8 == 6 else "O-O-O"
    return "%s%s→%s%s" % ("" if p in "P." else p, mv[:2], mv[2:4], ("=" + mv[4].upper()) if len(mv) > 4 else "")


def describe_move(board, mv):
    fr, to = name_sq(mv[:2]), name_sq(mv[2:4])
    p = board[fr].lower()
    if p == "k" and abs(fr % 8 - to % 8) == 2:
        return "Castle " + ("kingside" if to % 8 == 6 else "queenside")
    text = "%s %s → %s" % (PIECE_NAMES.get(p, "Piece"), mv[:2], mv[2:4])
    if len(mv) > 4:
        text += " (promote to %s)" % PIECE_NAMES.get(mv[4], "?")
    return text


# =============================================================================
#  Worker thread: capture -> recognise -> engine -> arrows
# =============================================================================

class Settings:
    def __init__(self, cfg):
        self.think = float(cfg.get("think", 0.5))
        self.both = bool(cfg.get("both", False))
        self.top3 = bool(cfg.get("top3", True))
        self.elo = int(cfg.get("elo", 0))          # 0 = full strength
        self.eval_bar = bool(cfg.get("eval_bar", True))
        self.beep = bool(cfg.get("beep", False))
        self.paused = False


class ExperimentLog:
    """Keeps score of how often the suggested move was played, game by game,
    in experiment_log.csv (opens in Excel / Google Sheets)."""

    HEADER = "time,game,you_play,position_fen,suggested,eval_for_white,you_played,followed\n"

    def __init__(self, path):
        self.path = path
        self.pending = None
        self.game = None
        self.followed = 0
        self.total = 0

    def observe(self, game_id, board):
        """Call with every new position; scores the last suggestion once you've moved."""
        if game_id != self.game:
            self.game, self.pending = game_id, None
            return False
        p = self.pending
        if p is None or board == p["board"]:
            return False
        self.pending = None
        played = infer_move(p["board"], board, p["white"])
        if played is None:
            return False
        followed = played == p["move"]
        self.total += 1
        self.followed += followed
        try:
            new = not os.path.exists(self.path)
            with open(self.path, "a", encoding="utf-8") as f:
                if new:
                    f.write(self.HEADER)
                f.write("%s,%d,%s,%s,%s,%s,%s,%s\n" % (
                    time.strftime("%Y-%m-%d %H:%M:%S"), game_id, "white" if p["white"] else "black",
                    p["fen"], p["move"], p["eval"], played, "yes" if followed else "no"))
        except OSError:
            pass
        return True

    def suggest(self, game_id, fen, board, white, move, score):
        self.game = game_id
        self.pending = dict(fen=fen, board=list(board), white=white, move=move,
                            eval=format_eval(white_pov(score, "w" if white else "b")))


class Worker(threading.Thread):
    def __init__(self, ui_q, settings, cfg):
        super().__init__(daemon=True)
        self.ui = ui_q
        self.settings = settings
        self.cfg = cfg
        self.cmds = queue.Queue()
        self.geom = None
        self.downloader = None    # thread fetching Stockfish on first run
        self.book = None          # piece thumbnails for the current board style
        self.book_file = None
        self.book_saved = 0.0
        self.book_added = 0
        self.last_det = None
        self.experiment = ExperimentLog(os.path.join(DATA_DIR, "experiment_log.csv"))
        self.tracker = GameTracker()
        self.engine = None
        self.engine_missing = False
        self.overlay_hidden_from_capture = True
        self.capture_evt = threading.Event()
        self.arrows_drawn = False
        self.stop_flag = False
        self.dirty = False
        self.stable = None
        self.candidate = None
        self.start_seen = 0
        self.lost_frames = 0
        self.unknown_frames = 0
        self.last_search = 0.0
        self.last_any_search = 0.0
        self._status = None

    # ---- messages to the UI ----
    def status(self, text):
        if text != self._status:
            self._status = text
            self.ui.put(("status", text))

    def show(self, arrows, text="", sub=""):
        self.arrows_drawn = bool(arrows)
        self.ui.put(("arrows", arrows))
        self.ui.put(("move", text, sub))

    # ---- screen capture ----
    def grab(self, region):
        hide = (not self.overlay_hidden_from_capture) and self.arrows_drawn
        if hide:  # fallback for old Windows: briefly hide the arrows while capturing
            self.capture_evt.clear()
            self.ui.put(("hide_for_capture",))
            self.capture_evt.wait(0.5)
        shot = self.sct.grab(region)
        if hide:
            self.ui.put(("show_after_capture",))
        return np.asarray(shot)[:, :, [2, 1, 0]]

    def palettes(self):
        pal = []
        if self.cfg.get("palette"):
            light, dark = self.cfg["palette"]
            pal.append((tuple(light), tuple(dark)))
        return pal + [p for p in KNOWN_PALETTES if p not in pal]

    def book_path(self):
        """One saved piece set per board style, so Chess.com and RoChess can both be remembered."""
        key = "".join("%x" % (int(v) >> 4) for v in list(self.geom["light"]) + list(self.geom["dark"]))
        return os.path.join(DATA_DIR, "pieces_%s.npz" % key)

    def set_board(self, geom, source):
        self.geom = geom
        if self.book_path() != self.book_file:      # different board style than before
            self.book_file = self.book_path()
            self.book = PieceBook.load(self.book_file)
            self.start_seen = 0
            self.tracker.reset()
        self.stable = self.candidate = None
        self.lost_frames = 0
        self.cfg["palette"] = [list(geom["light"]), list(geom["dark"])]
        save_config(self.cfg)
        self.ui.put(("geom", (geom["x"], geom["y"], geom["size"])))
        log("Board %s at x=%d y=%d size=%d" % (source, geom["x"], geom["y"], geom["size"]))

    def lose_board(self):
        if self.geom is not None:
            log("Board lost")
        self.geom = None
        self.stable = self.candidate = None
        self.ui.put(("geom", None))
        self.show([])

    def search_board(self):
        mon = self.sct.monitors[0]
        img = self.grab(mon)
        found = find_board(img, self.palettes())
        if found is None and time.time() - self.last_any_search >= ANY_STYLE_EVERY:
            self.last_any_search = time.time()
            found = find_board(img, any_board_palettes(img))
        if found:
            found["x"] += mon["left"]
            found["y"] += mon["top"]
            self.set_board(found, "found")

    def engine_note(self, text):
        self.ui.put(("engine", text))

    def start_engine_download(self):
        if self.downloader is not None and self.downloader.is_alive():
            return

        def job():
            while not self.stop_flag:
                try:
                    path = download_stockfish(self.engine_note)
                    log("Stockfish ready: " + path)
                    self.engine_note("Stockfish is ready ✓")
                    self.cmds.put(("dirty",))
                    return
                except Exception as e:
                    log("Stockfish download failed: %s" % e)
                    self.engine_note("Couldn't download the Stockfish chess engine. Check your internet / "
                                     "VPN - I'll try again in a minute. Or put stockfish.exe into: %s"
                                     % ENGINE_DIR)
                for _ in range(600):              # wait a minute (or until the app closes / it appears)
                    if self.stop_flag or find_stockfish():
                        break
                    threading.Event().wait(0.1)
                if find_stockfish():
                    self.engine_note("")
                    self.cmds.put(("dirty",))
                    return

        self.downloader = threading.Thread(target=job, daemon=True)
        self.downloader.start()

    def get_engine(self):
        if self.engine is not None and self.engine.proc.poll() is None:
            return self.engine
        if self.downloader is not None and self.downloader.is_alive():
            self.status("Waiting for the chess engine…")
            return None
        path = find_stockfish()
        if not path:
            self.start_engine_download()
            self.status("Waiting for the chess engine…")
            return None
        try:
            self.engine = Engine(path)
            log("Engine started: " + path)
            return self.engine
        except Exception as e:
            self.engine = None
            self.status("Could not start Stockfish: %s" % e)
            return None

    # ---- main loop ----
    def run(self):
        try:
            import mss
        except ImportError:
            self.status("The 'mss' package is missing. Run “Start Chess Overlay.bat” to install it."
                        if not FROZEN else "This copy of Chess Overlay is broken (mss missing) - rebuild it.")
            return
        self.sct = mss.mss()
        if find_stockfish() is None:      # get it now, so it's ready by the first move
            self.start_engine_download()
        while not self.stop_flag:
            try:
                self.step()
            except Exception as e:
                log("Error: " + traceback.format_exc())
                self.status("Error: %s (details in chess_overlay.log)" % e)
                time.sleep(1.0)
        if self.engine:
            self.engine.close()

    def handle_commands(self):
        while True:
            try:
                cmd = self.cmds.get_nowait()
            except queue.Empty:
                return
            kind = cmd[0]
            if kind == "find":
                self.lose_board()
                self.last_search = self.last_any_search = 0.0
            elif kind == "set_board":
                self.set_board(cmd[1], "selected")
            elif kind == "relearn":
                self.book = None
                self.start_seen = 0
                self.tracker.reset()
                self.stable = self.candidate = None
                if self.geom:
                    try:
                        os.remove(self.book_path())
                    except OSError:
                        pass
                self.show([])
            elif kind == "flip":
                self.tracker.flip()
                self.dirty = True
            elif kind == "dirty":
                self.dirty = True
            elif kind == "capture_mode":
                self.overlay_hidden_from_capture = cmd[1]

    def step(self):
        self.handle_commands()
        if self.settings.paused:
            self.status("Paused.")
            time.sleep(0.2)
            return

        if self.geom is None:
            if time.time() - self.last_search < 1.0:
                time.sleep(0.15)
                return
            self.last_search = time.time()
            self.search_board()
            if self.geom is None:
                self.status("Looking for a chess board… Open a game (Chess.com, RoChess…). "
                            "If nothing happens, click “Select board” and drag a box around it.")
                return

        g = self.geom
        img = self.grab({"left": g["x"], "top": g["y"], "width": g["size"], "height": g["size"]})
        infos = analyze_board(img, g["light"], g["dark"])
        good, bad = board_check([inf.cls for inf in infos], g.get("parity", 0))
        if good < 32 or bad > 6:
            self.lost_frames += 1
            if self.lost_frames >= 5:
                self.lose_board()
            time.sleep(0.1)
            return
        self.lost_frames = 0

        if self.book is None:
            if is_start_occupancy(infos):
                self.start_seen += 1
                if self.start_seen >= 2:
                    self.book = PieceBook.learn(infos)
                    self.book.save(self.book_path())
                    log("Learned piece set (threshold %.4f)" % self.book.threshold)
                    self.status("Learned your piece set ✓")
            else:
                self.start_seen = 0
                self.status("Board found! One-time setup: start a new game so the starting "
                            "position is on screen — I'll learn your pieces from it.")
            time.sleep(0.2)
            return

        grid, det = self.book.classify(infos, details=True)
        if grid is None:
            self.unknown_frames += 1
            if self.unknown_frames == 40:
                self.status("Some pieces don't look familiar. If you changed piece style, "
                            "click “Relearn pieces” and start a new game.")
            time.sleep(0.1)
            return
        self.unknown_frames = 0

        if grid != self.candidate:        # wait until the picture is steady
            self.candidate = grid
            time.sleep(0.08)
            return
        if grid == self.stable and not self.dirty:
            time.sleep(0.12)
            return
        self.last_det = det
        self.process(grid, infos)

    def learn_more(self, infos, grid):
        """Feed clear-cut examples back into the piece book (saved every 10 s at most)."""
        if self.last_det is None:
            return
        self.book_added += self.book.adapt(infos, grid, self.last_det)
        if self.book_added and time.time() - self.book_saved > 10:
            self.book.save(self.book_path())
            log("Piece book now has %d examples" % len(self.book.labels))
            self.book_saved = time.time()
            self.book_added = 0

    def process(self, grid, infos):
        changed = grid != self.stable
        self.stable = grid
        self.dirty = False
        if changed and self.arrows_drawn:
            self.show([])

        res = self.tracker.update(grid, infos)
        if "error" in res:
            self.status("That position doesn't look legal (%s) — waiting for a clearer view…" % res["error"])
            self.show([])
            return
        if changed:
            self.learn_more(infos, grid)
        wb = res["white_bottom"]
        g = self.geom
        self.ui.put(("seen", grid, g["light"], g["dark"]))
        if self.experiment.observe(self.tracker.game_id, res["board"]):
            self.ui.put(("stats", self.experiment.followed, self.experiment.total))

        you = "w" if wb else "b"
        your_turn = res["turn"] == you
        if not your_turn and not self.settings.both:
            self.status("Bot's turn — waiting…")
            self.show([])
            return

        engine = self.get_engine()
        if engine is None:
            return
        self.status("Thinking…")
        try:
            engine.configure(3 if self.settings.top3 else 1, self.settings.elo)
            mv, lines = engine.analyse(res["fen"], self.settings.think)
        except Exception as e:
            log("Engine error: %s" % e)
            if self.engine:
                self.engine.close()
            self.engine = None
            self.dirty = True
            return
        score = next((sc for m, sc, _ in lines if m == mv), lines[0][1] if lines else None)
        log("%s -> %s %s %s" % (res["fen"], mv, score, [l[0] for l in lines]))
        if mv is None:
            self.status("No legal moves — game over.")
            self.show([])
            return

        board = res["board"]
        color = YOUR_COLOR if your_turn else BOT_COLOR
        arrows = []
        alts = []
        for rank, m in enumerate([mv] + [l[0] for l in lines if l[0] != mv][:2 if self.settings.top3 else 0]):
            r0, c0 = sq_to_screen(name_sq(m[:2]), wb)
            r1, c1 = sq_to_screen(name_sq(m[2:4]), wb)
            arrows.append((r0, c0, r1, c1, color, m[4].upper() if len(m) > 4 else "", rank + 1))
            if rank:
                sc = next((sc for mm, sc, _ in lines if mm == m), None)
                alts.append("%s (%s)" % (short_move(board, m), format_eval(white_pov(sc, res["turn"]))))
        who = "Your move" if your_turn else "Bot's best move"
        text = "%s: %s" % (who, describe_move(board, mv))
        sub = ("Also good: " + "   ".join(alts)) if alts else ""
        self.show(arrows, text, sub)
        self.ui.put(("eval", white_pov(score, res["turn"]), wb))
        if your_turn:
            self.experiment.suggest(self.tracker.game_id, res["fen"], board, wb, mv, score)
            if changed and self.settings.beep and IS_WINDOWS:
                try:
                    import winsound
                    winsound.MessageBeep()
                except Exception:
                    pass
        note = " · eval %s" % format_eval(white_pov(score, res["turn"])) if score else ""
        if self.settings.elo:
            note += " · playing like %d Elo" % self.settings.elo
        if res["how"] == "guess":
            note += " · (turn guessed)"
        self.status(("Your turn" if your_turn else "Bot's turn") + note)


# =============================================================================
#  Config
# =============================================================================

def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


# =============================================================================
#  Windows helpers
# =============================================================================

def set_dpi_awareness():
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def make_overlay_window(tk_window):
    """Click-through + hidden from screen capture. Returns True if capture-hiding worked."""
    if not IS_WINDOWS:
        return False
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    hwnd = user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()
    GWL_EXSTYLE = -20
    WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x08000000
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
    try:
        user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        return bool(user32.SetWindowDisplayAffinity(hwnd, 0x11))  # WDA_EXCLUDEFROMCAPTURE
    except Exception:
        return False


def start_hotkey_thread(callback, vk=0x77):
    """Global F8 hotkey."""
    if not IS_WINDOWS:
        return

    def loop():
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, 0x4000, vk):  # MOD_NOREPEAT
            log("F8 hotkey is taken by another program")
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                callback()

    threading.Thread(target=loop, daemon=True).start()


# =============================================================================
#  User interface
# =============================================================================

KEY_COLOR = "#FF00FE"   # painted pixels of this colour are see-through
UI_BG = "#1E1F24"
UI_CARD = "#2B2D35"
UI_FG = "#ECECEE"
UI_MUTED = "#9EA1AA"
UI_ACCENT = "#FF9F1C"
ALT_COLOR = "#FFE2A8"   # 2nd / 3rd best move arrows
OUTLINE = "#1A1A1A"
FONT = "Segoe UI"
PIECE_FONT = "Segoe UI Symbol"
SOLID = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
HOLLOW = {"k": "♔", "q": "♕", "r": "♖", "b": "♗", "n": "♘", "p": "♙"}
MAX_ELO = 3200          # slider position that means "no limit"


def white_fraction(score):
    """Share of the eval bar that is white, from a White's-view score."""
    if score is None:
        return 0.5
    kind, v = score
    if kind == "mate":
        return 1.0 if v > 0 else (0.0 if v < 0 else 0.5)
    return 1.0 / (1.0 + math.exp(-v / 250.0))


def format_eval(score):
    if score is None:
        return "–"
    kind, v = score
    if kind == "mate":
        return ("M%d" % v) if v > 0 else ("-M%d" % -v) if v < 0 else "#"
    return "%+.1f" % (v / 100.0)


def virtual_screen_left():
    if IS_WINDOWS:
        try:
            return ctypes.windll.user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        except Exception:
            pass
    return 0


class App:
    MINI = 24  # square size of the little "what I see" board

    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.cfg = load_config()
        self.settings = Settings(self.cfg)
        self.q = queue.Queue()
        self.worker = Worker(self.q, self.settings, self.cfg)
        self.geom = None
        self.arrows = []
        self.visible = True
        self.eval = None            # latest score, White's view
        self.white_bottom = True
        self.seen = None            # (grid, light, dark) of the last position read
        self.board_off = 0          # x of the board inside the overlay window
        self.bar = None             # (x, width) of the eval bar inside the overlay window

        root = self.root = tk.Tk()
        root.title("Chess Overlay")
        root.configure(bg=UI_BG)
        icon = os.path.join(RES_DIR, "icon.ico")
        if IS_WINDOWS and os.path.exists(icon):
            try:
                root.iconbitmap(default=icon)
            except Exception:
                pass
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.geometry("+40+40")

        body = tk.Frame(root, bg=UI_BG, padx=16, pady=14)
        body.pack(fill="both")

        def label(parent, var=None, text="", size=10, bold=False, fg=UI_FG, **kw):
            lb = tk.Label(parent, text=text, bg=parent["bg"], fg=fg, justify="left", anchor="w",
                          font=(FONT, size, "bold" if bold else "normal"), **kw)
            if var is not None:
                lb.config(textvariable=var)
            return lb

        def button(parent, text, cmd):
            return tk.Button(parent, text=text, command=cmd, bg=UI_CARD, fg=UI_FG, relief="flat", bd=0,
                             activebackground="#3B3E48", activeforeground=UI_FG, padx=10, pady=5,
                             font=(FONT, 9), cursor="hand2")

        def check(text, value, cmd):
            var = tk.BooleanVar(value=value)
            tk.Checkbutton(body, text=text, variable=var, command=cmd, bg=UI_BG, fg=UI_FG,
                           activebackground=UI_BG, activeforeground=UI_FG, selectcolor=UI_CARD,
                           font=(FONT, 9), anchor="w", bd=0, highlightthickness=0).pack(fill="x")
            return var

        def section(title):
            label(body, text=title, size=8, bold=True, fg=UI_MUTED).pack(fill="x", pady=(14, 4))

        def slider(lo, hi, step, cmd):
            row = tk.Frame(body, bg=UI_BG)
            row.pack(fill="x")
            sc = tk.Scale(row, from_=lo, to=hi, resolution=step, orient="horizontal", length=240,
                          showvalue=0, bg=UI_BG, fg=UI_FG, troughcolor=UI_CARD, activebackground=UI_ACCENT,
                          highlightthickness=0, bd=0, sliderrelief="flat", command=cmd)
            sc.pack(side="left")
            var = tk.StringVar()
            label(row, var, size=9).pack(side="left", padx=(10, 0))
            return sc, var

        label(body, text="♞  Chess Overlay", size=14, bold=True).pack(fill="x")

        # --- what the app sees + evaluation ---
        top = tk.Frame(body, bg=UI_BG)
        top.pack(fill="x", pady=(10, 0))
        self.mini = tk.Canvas(top, width=8 * self.MINI, height=8 * self.MINI, bg=UI_CARD, highlightthickness=0)
        self.mini.pack(side="left")
        info = tk.Frame(top, bg=UI_BG, padx=14)
        info.pack(side="left", fill="both", expand=True)
        self.eval_var = tk.StringVar(value="–")
        label(info, self.eval_var, size=26, bold=True).pack(fill="x")
        label(info, text="evaluation\n+ = White is better", size=8, fg=UI_MUTED).pack(fill="x")
        self.mini_bar = tk.Canvas(info, width=120, height=10, bg="#3B3B3B", highlightthickness=0)
        self.mini_bar.pack(anchor="w", pady=(8, 0))
        label(info, text="what I see ←", size=8, fg=UI_MUTED).pack(fill="x", pady=(18, 0))

        self.move_var = tk.StringVar(value="")
        self.sub_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Starting…")
        label(body, self.move_var, size=12, bold=True, fg=UI_ACCENT, wraplength=340).pack(fill="x", pady=(12, 0))
        label(body, self.sub_var, size=9, fg="#D9C9A8", wraplength=340).pack(fill="x")
        label(body, self.status_var, size=9, fg=UI_MUTED, wraplength=340).pack(fill="x", pady=(4, 0))
        self.engine_var = tk.StringVar(value="")
        label(body, self.engine_var, size=9, fg="#7FC8FF", wraplength=340).pack(fill="x")

        row = tk.Frame(body, bg=UI_BG)
        row.pack(fill="x", pady=(12, 0))
        self.pause_btn = button(row, "Pause", self.toggle_pause)
        self.pause_btn.pack(side="left")
        button(row, "Find board", lambda: self.worker.cmds.put(("find",))).pack(side="left", padx=6)
        button(row, "Select board…", self.select_board).pack(side="left")
        row = tk.Frame(body, bg=UI_BG)
        row.pack(fill="x", pady=(6, 0))
        button(row, "Flip board", lambda: self.worker.cmds.put(("flip",))).pack(side="left")
        button(row, "Relearn pieces", self.relearn).pack(side="left", padx=6)

        section("SHOW")
        self.top3_var = check("Top 3 moves (thin arrows = 2nd and 3rd best)", self.settings.top3, self.on_top3)
        self.bar_var = check("Eval bar next to the board", self.settings.eval_bar, self.on_bar)
        self.both_var = check("The bot's best move too (blue arrow)", self.settings.both, self.on_both)
        self.beep_var = check("Beep when it's my turn", self.settings.beep, self.on_beep)

        section("ENGINE STRENGTH")
        self.elo_scale, self.elo_var = slider(1350, MAX_ELO, 50, self.on_elo)
        self.elo_scale.set(self.settings.elo or MAX_ELO)
        self.on_elo(self.settings.elo or MAX_ELO)
        section("THINK TIME PER MOVE")
        self.think_scale, self.think_var = slider(0.1, 3.0, 0.1, self.on_think)
        self.think_scale.set(self.settings.think)
        self.on_think(self.settings.think)

        section("EXPERIMENT")
        self.stats_var = tk.StringVar(value="No moves scored yet.")
        label(body, self.stats_var, size=9, wraplength=340).pack(fill="x")
        row = tk.Frame(body, bg=UI_BG)
        row.pack(fill="x", pady=(6, 0))
        button(row, "Open experiment log", self.open_log).pack(side="left")
        button(row, "Open app folder", self.open_folder).pack(side="left", padx=6)
        label(body, text="F8 hides / shows the arrows", size=8, fg=UI_MUTED).pack(fill="x", pady=(12, 0))

        # ---- the transparent, click-through window on top of the board ----
        ov = self.ov = tk.Toplevel(root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        if IS_WINDOWS:
            ov.attributes("-transparentcolor", KEY_COLOR)
            ov.attributes("-alpha", 0.88)
        ov.configure(bg=KEY_COLOR)
        self.cv = tk.Canvas(ov, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        ov.geometry("1x1+0+0")
        root.after(300, self.setup_overlay)

        self.draw_mini()
        self.show_eval()
        start_hotkey_thread(lambda: self.q.put(("toggle_visible",)))
        root.after(50, self.poll)
        self.worker.start()

    def setup_overlay(self):
        self.ov.update_idletasks()
        try:
            hidden = make_overlay_window(self.ov)
        except Exception:
            log("Overlay setup failed: " + traceback.format_exc())
            hidden = False
        if not hidden:
            log("Window capture-exclusion unavailable; arrows will blink off during captures.")
        self.worker.cmds.put(("capture_mode", hidden))

    # ---- controls ----
    def save(self, key, value, recompute=True):
        self.cfg[key] = value
        save_config(self.cfg)
        if recompute:
            self.worker.cmds.put(("dirty",))

    def toggle_pause(self):
        self.settings.paused = not self.settings.paused
        self.pause_btn.config(text="Resume" if self.settings.paused else "Pause")
        if self.settings.paused:
            self.arrows = []
            self.redraw()
            self.move_var.set("")
            self.sub_var.set("")
        else:
            self.worker.cmds.put(("dirty",))

    def relearn(self):
        self.worker.cmds.put(("relearn",))

    def on_top3(self):
        self.settings.top3 = bool(self.top3_var.get())
        self.save("top3", self.settings.top3)

    def on_bar(self):
        self.settings.eval_bar = bool(self.bar_var.get())
        self.save("eval_bar", self.settings.eval_bar, recompute=False)
        self.place_overlay()

    def on_both(self):
        self.settings.both = bool(self.both_var.get())
        self.save("both", self.settings.both)

    def on_beep(self):
        self.settings.beep = bool(self.beep_var.get())
        self.save("beep", self.settings.beep, recompute=False)

    def on_elo(self, value):
        v = int(float(value))
        self.settings.elo = 0 if v >= MAX_ELO else v
        self.elo_var.set("Full strength" if not self.settings.elo else "plays like %d Elo" % v)
        self.save("elo", self.settings.elo)

    def on_think(self, value):
        self.settings.think = float(value)
        self.think_var.set("%.1f s" % self.settings.think)
        self.save("think", self.settings.think, recompute=False)

    def open_log(self):
        path = self.worker.experiment.path
        if not os.path.exists(path):
            from tkinter import messagebox
            messagebox.showinfo("Chess Overlay", "No moves scored yet. Play a few moves with the "
                                "overlay running and the log will appear.")
            return
        if IS_WINDOWS:
            os.startfile(path)

    def open_folder(self):
        if IS_WINDOWS:
            os.startfile(DATA_DIR)

    def close(self):
        self.worker.stop_flag = True
        save_config(self.cfg)
        self.root.after(200, self.root.destroy)

    # ---- messages from the worker ----
    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status_var.set(msg[1])
                elif kind == "move":
                    self.move_var.set(msg[1])
                    self.sub_var.set(msg[2] if len(msg) > 2 else "")
                elif kind == "geom":
                    self.geom = msg[1]
                    if self.geom is None:
                        self.eval = None
                        self.show_eval()
                    self.place_overlay()
                elif kind == "arrows":
                    self.arrows = msg[1]
                    self.redraw()
                    self.draw_mini()
                elif kind == "eval":
                    self.eval, self.white_bottom = msg[1], msg[2]
                    self.show_eval()
                    self.redraw()
                elif kind == "seen":
                    self.seen = msg[1:]
                    self.draw_mini()
                elif kind == "engine":
                    self.engine_var.set(msg[1])
                    if msg[1].endswith("✓"):
                        self.root.after(4000, lambda: self.engine_var.set(""))
                elif kind == "stats":
                    followed, total = msg[1], msg[2]
                    self.stats_var.set("You played the suggested move %d of %d times (%d%%)."
                                       % (followed, total, round(100.0 * followed / total)))
                elif kind == "hide_for_capture":
                    self.cv.itemconfigure("all", state="hidden")
                    self.ov.update_idletasks()
                    self.root.after(40, self.worker.capture_evt.set)
                elif kind == "show_after_capture":
                    if self.visible:
                        self.cv.itemconfigure("all", state="normal")
                elif kind == "toggle_visible":
                    self.visible = not self.visible
                    self.redraw()
        except queue.Empty:
            pass
        self.root.after(40, self.poll)

    def show_eval(self):
        self.eval_var.set(format_eval(self.eval))
        self.mini_bar.delete("all")
        w = int(self.mini_bar["width"])
        self.mini_bar.create_rectangle(0, 0, w * white_fraction(self.eval), 12, fill="#F2F2F2", width=0)

    # ---- the overlay window ----
    def place_overlay(self):
        if self.geom is None:
            self.bar = None
            self.ov.geometry("1x1+0+0")
            self.redraw()
            return
        x, y, size = self.geom
        bw = max(10, size // 40) if self.settings.eval_bar else 0
        gap = 6 if bw else 0
        if bw and x - bw - gap >= virtual_screen_left():     # eval bar on the left of the board
            ox, self.board_off, self.bar = x - bw - gap, bw + gap, (0, bw)
        else:                                                # ... or on the right
            ox, self.board_off = x, 0
            self.bar = (size + gap, bw) if bw else None
        self.ov.geometry("%dx%d+%d+%d" % (size + bw + gap, size, ox, y))  # "+-100" = left of main screen
        self.redraw()

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        if not self.visible or not self.geom:
            return
        size = self.geom[2]
        s = size / 8.0
        if self.bar and self.eval is not None:
            bx, bw = self.bar
            wh = white_fraction(self.eval) * size
            cv.create_rectangle(bx, 0, bx + bw, size, fill="#3B3B3B", outline=OUTLINE)
            if self.white_bottom:
                cv.create_rectangle(bx + 1, size - wh, bx + bw - 1, size - 1, fill="#F2F2F2", width=0)
            else:
                cv.create_rectangle(bx + 1, 1, bx + bw - 1, wh, fill="#F2F2F2", width=0)
            cv.create_line(bx, size / 2, bx + bw, size / 2, fill=UI_ACCENT, width=2)
        ox = self.board_off
        for r0, c0, r1, c1, color, promo, rank in sorted(self.arrows, key=lambda a: -a[6]):
            x0, y0 = ox + (c0 + 0.5) * s, (r0 + 0.5) * s
            x1, y1 = ox + (c1 + 0.5) * s, (r1 + 0.5) * s
            dx, dy = x1 - x0, y1 - y0
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            if rank == 1:
                ring = s * 0.44
                lw = max(3, int(s * 0.07))
                cv.create_oval(x0 - ring, y0 - ring, x0 + ring, y0 + ring, outline=OUTLINE, width=lw + 3)
                cv.create_oval(x0 - ring, y0 - ring, x0 + ring, y0 + ring, outline=color, width=lw)
                bx0, by0 = ox + c1 * s + 3, r1 * s + 3
                cv.create_rectangle(bx0, by0, bx0 + s - 6, by0 + s - 6, outline=OUTLINE, width=lw + 3)
                cv.create_rectangle(bx0, by0, bx0 + s - 6, by0 + s - 6, outline=color, width=lw)
                width, head, line_color = max(5, int(s * 0.16)), (s * 0.42, s * 0.42, s * 0.2), color
            else:
                ring = s * 0.2
                width, head, line_color = max(3, int(s * 0.07)), (s * 0.28, s * 0.28, s * 0.12), ALT_COLOR
            sx, sy = x0 + ux * ring, y0 + uy * ring
            ex, ey = x1 - ux * s * 0.12, y1 - uy * s * 0.12
            cv.create_line(sx, sy, ex, ey, fill=OUTLINE, width=width + 4, arrow="last",
                           arrowshape=(head[0] + 3, head[1] + 3, head[2] + 2), capstyle="round")
            cv.create_line(sx, sy, ex, ey, fill=line_color, width=width, arrow="last",
                           arrowshape=head, capstyle="round")
            if rank > 1:   # numbered badge on the piece
                rr = s * 0.17
                cv.create_oval(x0 - rr, y0 - rr, x0 + rr, y0 + rr, fill=ALT_COLOR, outline=OUTLINE, width=2)
                cv.create_text(x0, y0, text=str(rank), fill=OUTLINE, font=(FONT, max(8, int(s * 0.17)), "bold"))
            if promo:
                cv.create_text(x1, y1 - s * 0.3, text="=" + promo, fill=line_color,
                               font=(FONT, max(10, int(s * 0.22)), "bold"))

    def draw_mini(self):
        cv = self.mini
        S = self.MINI
        cv.delete("all")
        if not self.seen:
            cv.create_text(4 * S, 4 * S, text="no board yet", fill=UI_MUTED, font=(FONT, 9))
            return
        grid, light, dark = self.seen
        colors = ("#%02x%02x%02x" % tuple(light), "#%02x%02x%02x" % tuple(dark))
        for i, ch in enumerate(grid):
            r, c = divmod(i, 8)
            cv.create_rectangle(c * S, r * S, (c + 1) * S, (r + 1) * S, fill=colors[(r + c) % 2], width=0)
            if ch == ".":
                continue
            x, y = c * S + S / 2, r * S + S / 2 + 1
            font = (PIECE_FONT, int(S * 0.62))
            if ch.isupper():     # white piece: white body + dark outline
                cv.create_text(x, y, text=SOLID[ch.lower()], fill="#FFFFFF", font=font)
                cv.create_text(x, y, text=HOLLOW[ch.lower()], fill="#111111", font=font)
            else:
                cv.create_text(x, y, text=SOLID[ch], fill="#111111", font=font)
        for r0, c0, r1, c1, color, promo, rank in sorted(self.arrows, key=lambda a: -a[6]):
            cv.create_line((c0 + 0.5) * S, (r0 + 0.5) * S, (c1 + 0.5) * S, (r1 + 0.5) * S,
                           fill=color if rank == 1 else ALT_COLOR, width=4 if rank == 1 else 2,
                           arrow="last", arrowshape=(9, 10, 4) if rank == 1 else (6, 7, 3))

    # ---- manual board selection ----
    def select_board(self):
        self.root.withdraw()
        self.cv.delete("all")
        self.root.after(250, self._select_capture)

    def _select_capture(self):
        tk = self.tk
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[0]
            shot = np.asarray(sct.grab(mon))[:, :, [2, 1, 0]]
            prim = sct.monitors[1] if len(sct.monitors) > 1 else mon
        sel = tk.Toplevel(self.root)
        sel.overrideredirect(True)
        sel.attributes("-topmost", True)
        sel.attributes("-alpha", 0.35)
        sel.geometry("%dx%d+%d+%d" % (mon["width"], mon["height"], mon["left"], mon["top"]))
        cv = tk.Canvas(sel, bg="black", highlightthickness=0, cursor="crosshair")
        cv.pack(fill="both", expand=True)
        cx = prim["left"] - mon["left"] + prim["width"] // 2
        cy = prim["top"] - mon["top"] + 60
        cv.create_text(cx, cy, text="Drag a box around the chess board   ·   Esc to cancel",
                       fill="white", font=("Segoe UI", 20, "bold"))
        state = {"start": None, "rect": None}

        def press(e):
            state["start"] = (e.x_root, e.y_root)

        def drag(e):
            if not state["start"]:
                return
            x0, y0 = state["start"]
            if state["rect"]:
                cv.delete(state["rect"])
            state["rect"] = cv.create_rectangle(x0 - mon["left"], y0 - mon["top"],
                                                e.x_root - mon["left"], e.y_root - mon["top"],
                                                outline="#FF9F1C", width=3)

        def finish(rect):
            sel.destroy()
            self.root.deiconify()
            self.redraw()
            if rect is None:
                return
            found = board_from_selection(shot, rect)
            if found is None:
                from tkinter import messagebox
                messagebox.showwarning("Chess Overlay", "I couldn't find a chess board inside that box. "
                                       "Try dragging just around the board's edges.")
                return
            found["x"] += mon["left"]
            found["y"] += mon["top"]
            self.worker.cmds.put(("set_board", found))

        def release(e):
            if not state["start"]:
                return
            x0, y0 = state["start"]
            finish((min(x0, e.x_root) - mon["left"], min(y0, e.y_root) - mon["top"],
                    max(x0, e.x_root) - mon["left"], max(y0, e.y_root) - mon["top"]))

        cv.bind("<ButtonPress-1>", press)
        cv.bind("<B1-Motion>", drag)
        cv.bind("<ButtonRelease-1>", release)
        sel.bind("<Escape>", lambda e: finish(None))
        sel.focus_force()

    def run(self):
        self.root.mainloop()


def message_box(text, error=False):
    if IS_WINDOWS:
        try:
            ctypes.windll.user32.MessageBoxW(None, text, "Chess Overlay", 0x10 if error else 0x40)
            return
        except Exception:
            pass
    print(text)


_INSTANCE_LOCK = None


def already_running():
    """True if another Chess Overlay is open (two would fight over F8 and the arrows)."""
    global _INSTANCE_LOCK
    if not IS_WINDOWS:
        return False
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        _INSTANCE_LOCK = k32.CreateMutexW(None, False, "Local\\ChessOverlay.SingleInstance")
        return ctypes.get_last_error() == 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def main():
    set_dpi_awareness()
    if already_running():
        message_box("Chess Overlay is already running. Look for its window - it may be behind "
                    "other windows or minimised on the taskbar.")
        return
    log("Chess Overlay starting (%s, data in %s)" % ("exe" if FROZEN else "script", DATA_DIR))
    try:
        App().run()
    except Exception as e:
        log("Crash: " + traceback.format_exc())
        message_box("Chess Overlay hit an error and has to close:\n\n%s\n\nDetails are in:\n%s"
                    % (e, LOG_PATH), error=True)


if __name__ == "__main__":
    main()
