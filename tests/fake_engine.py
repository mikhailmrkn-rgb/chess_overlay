#!/usr/bin/env python3
"""A tiny stand-in for Stockfish that speaks enough UCI for the tests.
It doesn't play chess: it always offers the same three moves for each side."""
import sys
import time

WHITE = [("e2e4", 34), ("d2d4", 28), ("g1f3", 20)]
BLACK = [("e7e5", -30), ("c7c5", -35), ("e7e6", -40)]
multipv, limited, fen = 1, False, ""
for line in sys.stdin:
    cmd = line.strip()
    if cmd == "uci":
        print("id name FakeFish")
        print("uciok", flush=True)
    elif cmd == "isready":
        print("readyok", flush=True)
    elif cmd.startswith("setoption name MultiPV value"):
        multipv = int(cmd.split()[-1])
    elif cmd.startswith("setoption name UCI_LimitStrength value"):
        limited = cmd.endswith("true")
    elif cmd.startswith("position fen"):
        fen = cmd[len("position fen "):]
    elif cmd.startswith("go movetime"):
        time.sleep(int(cmd.split()[2]) / 1000.0)
        if fen.startswith("7k/5Q2/6K1"):            # stalemate: no moves
            print("info depth 0 score mate 0")
            print("bestmove (none)", flush=True)
            continue
        moves = WHITE if fen.split()[1] == "w" else BLACK
        for k in range(multipv):
            mv, cp = moves[k]
            print("info depth 12 seldepth 15 multipv %d score cp %d nodes 99 pv %s" % (k + 1, cp, mv))
        print("bestmove %s" % (moves[1][0] if limited else moves[0][0]), flush=True)
    elif cmd == "quit":
        break
