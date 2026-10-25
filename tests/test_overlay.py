"""Tests for the board reader, chess logic, engine wrapper and the main loop.
Run with:  pytest tests"""
import functools
import http.server
import os
import queue
import shutil
import stat
import sys
import threading
import zipfile

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import chess_overlay as co  # noqa: E402
import sim  # noqa: E402
from sim import GAME, GREEN, BROWN, START, apply, board_list, hl_idx, render_board, render_screen, to_grid  # noqa: E402

pytestmark = pytest.mark.skipif(sim.FONT is None, reason="needs the DejaVu Sans font to draw pieces")
FAKE_ENGINE = os.path.join(HERE, "fake_engine.py")
POSIX = os.name == "posix"


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Keep settings / learned pieces / logs of every test in a temp folder."""
    monkeypatch.setattr(co, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(co, "ENGINE_DIR", str(tmp_path / "stockfish"))
    monkeypatch.setattr(co, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(co, "LOG_PATH", str(tmp_path / "test.log"))
    if POSIX:
        os.chmod(FAKE_ENGINE, os.stat(FAKE_ENGINE).st_mode | stat.S_IXUSR)


# --------------------------------------------------------------------------------------
#  Reading boards
# --------------------------------------------------------------------------------------

STYLES = {
    "chesscom-green-white": dict(palette=GREEN, s=80, wb=True),
    "lichess-brown-black": dict(palette=BROWN, s=64, wb=False),
    "big-board": dict(palette=GREEN, s=104, wb=True, x=120, y=40),
    "roblox-blue-gaps-busy-background": dict(palette=((210, 214, 230), (98, 110, 160)), s=72, wb=True,
                                             gap=2, hl=(120, 200, 255), noisy=True),
    "purple-black-red-highlight": dict(palette=((242, 230, 255), (150, 95, 190)), s=60, wb=False,
                                       hl=(255, 120, 120), noisy=True),
    "dark-top-left-square": dict(palette=((235, 220, 190), (120, 80, 50)), s=80, wb=True, gap=3,
                                 dark_first=True),
}


def draw(style, pos, hl=()):
    kw = dict(white_bottom=style["wb"], gap=style.get("gap", 0), dark_first=style.get("dark_first", False),
              hl_color=style.get("hl", (255, 255, 51)))
    img = render_board(to_grid(pos, style["wb"]), style["s"], style["palette"], highlights=hl, **kw)
    return render_screen(img, x=style.get("x", 500), y=style.get("y", 120), noisy=style.get("noisy", False))


def find(screen):
    return co.find_board(screen, co.KNOWN_PALETTES) or co.find_board(screen, co.any_board_palettes(screen))


@pytest.mark.parametrize("name", list(STYLES))
def test_reads_a_whole_game(name):
    st = STYLES[name]
    screen = draw(st, START)
    g = find(screen)
    assert g is not None
    assert (abs(g["x"] - st.get("x", 500)), abs(g["y"] - st.get("y", 120))) <= (1, 1)
    assert abs(g["size"] - 8 * st["s"]) <= 2

    def crop(scr):
        return scr[g["y"]:g["y"] + g["size"], g["x"]:g["x"] + g["size"]]

    infos = co.analyze_board(crop(screen), g["light"], g["dark"])
    assert co.is_start_occupancy(infos)
    book = co.PieceBook.learn(infos)
    tracker = co.GameTracker()
    first = tracker.update(book.classify(infos), infos)
    assert first["fen"] == co.START_FEN and first["white_bottom"] == st["wb"]

    pos = START
    for i, mv in enumerate(GAME):
        pos = apply(pos, mv)
        infos = co.analyze_board(crop(draw(st, pos, hl_idx(mv, st["wb"]))), g["light"], g["dark"])
        good, bad = co.board_check([inf.cls for inf in infos], g["parity"])
        assert good >= 32 and bad <= 6
        grid, det = book.classify(infos, details=True)
        assert grid == to_grid(pos, st["wb"]), "misread after %s" % mv
        book.adapt(infos, grid, det)
        res = tracker.update(grid, infos)
        assert res["turn"] == ("b" if i % 2 == 0 else "w"), "wrong turn after %s" % mv
    assert res["fen"] == "r1br2k1/pp3ppp/2n2n2/8/1bBp4/5N2/PPP2PPP/RNBQ1RK1 w - - 0 1"


def test_en_passant_square_comes_from_the_highlight():
    st = STYLES["chesscom-green-white"]
    g = find(draw(st, START))
    infos = co.analyze_board(render_board(to_grid(START, True), 80), *GREEN)
    book = co.PieceBook.learn(infos)
    tracker = co.GameTracker()
    tracker.update(book.classify(infos), infos)
    pos = apply(START, "e2e4")
    infos = co.analyze_board(render_board(to_grid(pos, True), 80, highlights=hl_idx("e2e4", True)), *GREEN)
    assert tracker.update(book.classify(infos), infos)["fen"].endswith("b KQkq e3 0 1")
    assert g["parity"] == 0


def test_move_hint_dots_are_not_pieces():
    infos = co.analyze_board(render_board(to_grid(START, True), 80), *GREEN)
    book = co.PieceBook.learn(infos)
    pos = apply(START, "e2e4")
    img = render_board(to_grid(pos, True), 80, highlights=hl_idx("e2e4", True), dots=[43, 35])
    assert book.classify(co.analyze_board(img, *GREEN)) is None   # = "not sure, wait"


def test_select_board_learns_an_unknown_theme():
    theme = ((233, 237, 204), (75, 115, 153))
    screen = render_screen(render_board(to_grid(START, True), 80, theme), x=600, y=140)
    assert co.find_board(screen, co.KNOWN_PALETTES) is None
    found = co.board_from_selection(screen, (580, 110, 1265, 810))   # a sloppy box
    assert found and (found["x"], found["y"], found["size"]) == (600, 140, 640)
    again = co.find_board(screen, [(found["light"], found["dark"])])
    assert again and again["size"] == 640


def test_no_board_on_an_empty_screen():
    assert find(render_screen(np.zeros((1, 1, 3), np.uint8) + 49)) is None


def test_piece_book_learns_new_looks_but_not_junk(tmp_path):
    infos = co.analyze_board(render_board(to_grid(START, True), 80), *GREEN)
    book = co.PieceBook.learn(infos)
    rng = np.random.default_rng(0)
    queen = infos[59]
    variant = co.SquareInfo()
    variant.feat, variant.lum, variant.frac = queen.feat.copy(), queen.lum, queen.frac
    idx = rng.choice(len(queen.feat), 100, replace=False)
    variant.feat[idx] = np.clip(variant.feat[idx] + 0.3, 0, 1)
    seen = [variant if i == 59 else inf for i, inf in enumerate(infos)]
    grid, det = book.classify(seen, details=True)
    assert grid[59] == "Q"
    assert book.adapt(seen, grid, det) == 1 and book.labels.count("Q") == 2
    junk = co.SquareInfo()
    junk.feat, junk.lum, junk.frac = rng.random(len(queen.feat)).astype(np.float32), 0.5, 0.3
    assert book.classify([junk if i == 30 else inf for i, inf in enumerate(infos)]) is None
    path = str(tmp_path / "book.npz")
    book.save(path)
    assert co.PieceBook.load(path).labels == book.labels


# --------------------------------------------------------------------------------------
#  Chess logic
# --------------------------------------------------------------------------------------

def test_infer_move():
    pos = START
    for mv in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]:
        pos = apply(pos, mv)
    assert co.infer_move(board_list(pos), board_list(apply(pos, "e1g1")), True) == "e1g1"
    after_capture = apply(pos, "f3e5")
    assert co.infer_move(board_list(after_capture), board_list(apply(after_capture, "c6e5")), False) == "c6e5"
    promo = {co.name_sq("a7"): "P", co.name_sq("e1"): "K", co.name_sq("e8"): "k", co.name_sq("b8"): "n"}
    assert co.infer_move(board_list(promo), board_list(apply(promo, "a7b8q")), True) == "a7b8q"
    both_moved = apply(apply(START, "e2e4"), "d7d5")       # works even after the reply
    assert co.infer_move(board_list(START), board_list(both_moved), True) == "e2e4"


def test_illegal_positions_are_rejected():
    board = board_list({co.name_sq("e1"): "K", co.name_sq("e8"): "k", co.name_sq("e2"): "Q"})
    assert co.position_problem(board, "w") == "check"   # black can't be in check with white to move
    assert co.position_problem(board, "b") is None
    assert co.position_problem(board_list({co.name_sq("e1"): "K"}), "w") == "kings"


def test_mid_game_guess_checks_for_check():
    infos = co.analyze_board(render_board(to_grid(START, True), 80), *GREEN)
    book = co.PieceBook.learn(infos)
    pos = {co.name_sq(s): p for s, p in {"e1": "K", "e8": "k", "e2": "Q", "a2": "P", "h7": "p"}.items()}
    infos = co.analyze_board(render_board(to_grid(pos, True), 80), *GREEN)
    res = co.GameTracker().update(book.classify(infos), infos)
    assert res["turn"] == "b"   # black is in check, so it must be black's move


def test_scores_and_names():
    assert co.format_eval(("cp", 35)) == "+0.3" and co.format_eval(("mate", -3)) == "-M3"
    assert co.white_pov(("cp", 50), "b") == ("cp", -50)
    assert co.white_fraction(("mate", 2)) == 1.0 and co.white_fraction(None) == 0.5
    board = co.grid_to_board(to_grid(START, True), True)
    assert co.describe_move(board, "e1g1") == "Castle kingside"
    assert co.short_move(board, "g1f3") == "Ng1→f3"


# --------------------------------------------------------------------------------------
#  Engine
# --------------------------------------------------------------------------------------

needs_posix = pytest.mark.skipif(not POSIX, reason="the fake engine is a script started directly")


@needs_posix
def test_engine_top_moves_and_strength():
    e = co.Engine(FAKE_ENGINE)
    try:
        e.configure(3, 0)
        best, lines = e.analyse(co.START_FEN, 0.05)
        assert best == "e2e4" and [m for m, _, _ in lines] == ["e2e4", "d2d4", "g1f3"]
        assert lines[0][1] == ("cp", 34)
        e.configure(3, 1500)
        assert e.analyse(co.START_FEN, 0.05)[0] == "d2d4"
        assert e.best_move("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 0.05)[0] is None
    finally:
        e.close()


@needs_posix
def test_engine_download_picks_a_build_that_works(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg" / "stockfish"
    pkg.mkdir(parents=True)
    (pkg / "stockfish-x86-64-universal").write_text(   # crashes as soon as it has to think
        "#!/usr/bin/env python3\nimport sys\nfor l in sys.stdin:\n    c = l.strip()\n"
        "    if c == 'uci': print('uciok', flush=True)\n"
        "    elif c == 'isready': print('readyok', flush=True)\n"
        "    elif c.startswith('go'): sys.exit(132)\n")
    shutil.copy(FAKE_ENGINE, pkg / "stockfish-x86-64-avx2")
    (pkg / "COPYING.txt").write_text("GPL")
    www = tmp_path / "www"
    www.mkdir()
    with zipfile.ZipFile(www / "sf.zip", "w") as z:
        for f in pkg.iterdir():
            z.write(f, "stockfish/" + f.name)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(www))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(co, "STOCKFISH_URL", "http://127.0.0.1:%d/" % server.server_port)
        monkeypatch.setattr(co, "stockfish_zip_names", lambda: ["missing.zip", "sf.zip"])
        notes = []
        path = co.download_stockfish(notes.append)
        assert os.path.basename(path) == "stockfish-x86-64-avx2"
        assert co.find_stockfish() == path
        assert any("100%" in n for n in notes)
        assert not os.path.exists(os.path.join(co.ENGINE_DIR, "_download"))
    finally:
        server.shutdown()


# --------------------------------------------------------------------------------------
#  The main loop, end to end
# --------------------------------------------------------------------------------------

@needs_posix
def test_worker_end_to_end(monkeypatch):
    monkeypatch.setattr(co, "find_stockfish", lambda: FAKE_ENGINE)
    monkeypatch.setattr(co.time, "sleep", lambda s: None)
    ui = queue.Queue()
    w = co.Worker(ui, co.Settings({"think": 0.05}), {})
    w.sct = sim.FakeScreen()

    def show(pos, mv=None):
        hl = hl_idx(mv, True) if mv else ()
        w.sct.screen = render_screen(render_board(to_grid(pos, True), 80, GREEN, highlights=hl), x=600, y=140)

    def run(n):
        for _ in range(n):
            w.step()
        msgs = []
        while not ui.empty():
            msgs.append(ui.get())
        return msgs

    try:
        show(START)
        msgs = run(10)
        assert ("geom", (600, 140, 640)) in msgs
        arrows = [m[1] for m in msgs if m[0] == "arrows" and m[1]][-1]
        assert [a[6] for a in arrows] == [1, 2, 3] and arrows[0][:4] == (6, 4, 4, 4)   # e2 -> e4 first
        assert any(m[0] == "eval" and m[1] == ("cp", 34) for m in msgs)

        pos = apply(START, "e2e4")          # you followed the suggestion
        show(pos, "e2e4")
        assert ("stats", 1, 1) in run(4)
        pos = apply(pos, "e7e5")
        show(pos, "e7e5")
        run(4)
        pos = apply(pos, "g1f3")            # ...and this time you didn't
        show(pos, "g1f3")
        assert ("stats", 1, 2) in run(4)
        with open(w.experiment.path) as f:
            rows = f.read().splitlines()
        assert rows[0].startswith("time,game") and rows[1].endswith(",e2e4,yes") and rows[2].endswith(",g1f3,no")

        w.sct.screen = render_screen(np.zeros((1, 1, 3), np.uint8) + 49)   # board covered
        assert ("geom", None) in run(8)
    finally:
        if w.engine:
            w.engine.close()
