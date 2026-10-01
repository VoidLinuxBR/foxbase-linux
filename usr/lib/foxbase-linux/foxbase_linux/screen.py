"""Partes comuns das telas cheias (CREATE, EDIT/APPEND, BROWSE).

Layout no estilo dBASE III PLUS / FoxBASE+: caixa de ajuda no topo (F1 liga e
desliga), área de trabalho, barra de status na penúltima linha e linha de
mensagens na última.
"""

import curses
from pathlib import Path

from . import ui

HELP_EDIT = [
    ("CURSOR   <-- -->", "UP    DOWN", "DELETE", "Insert Mode:  Ins"),
    ("Char:     ←   →", "Field:  ↑  ↓", "Char:   Del", "Exit/Save:    ^End"),
    ("Word:   Home End", "Page: PgUp PgDn", "Field:  ^Y", "Abort:        Esc"),
    ("", "Help:   F1", "Record: ^U", ""),
]

HELP_APPEND = HELP_EDIT

HELP_BROWSE = [
    ("CURSOR   <-- -->", "UP    DOWN", "DELETE", "Insert Mode:  Ins"),
    ("Char:     ←   →", "Record: ↑  ↓", "Char:   Del", "Exit/Save:    ^End"),
    ("Field:  Home End", "Page: PgUp PgDn", "Field:  ^Y", "Abort:        Esc"),
    ("Pan:     ^← ^→", "Help:   F1", "Record: ^U", ""),
]

HELP_CREATE = [
    ("CURSOR   <-- -->", "INSERT", "DELETE", "Up a field:    ↑"),
    ("Char:     ←   →", "Char:  Ins", "Char:   Del", "Down a field:  ↓"),
    ("Word:   Home End", "Field: ^N", "Word:   ^Y", "Exit/Save:     ^End"),
    ("", "Help:  F1", "Field:  ^U", "Abort:         Esc"),
]

HELP_HEIGHT = 6  # caixa com 4 linhas + bordas


def clear(stdscr):
    ui.clear(stdscr)


def help_box(stdscr, lines):
    """Desenha a caixa de ajuda no topo; retorna a primeira linha livre."""
    _, w = stdscr.getmaxyx()
    ui.box(stdscr, 0, 0, len(lines) + 2, w, clear=True)
    cols = (2, 20, 39, 57)
    for row, parts in enumerate(lines, 1):
        for col, text in zip(cols, parts):
            attr = curses.A_BOLD if row == 1 else 0
            ui.put(stdscr, row, col, text, attr)
    return len(lines) + 2


def status_bar(stdscr, mode, filename="", info="", flags=""):
    h, w = stdscr.getmaxyx()
    attr = curses.color_pair(ui.C_REVERSE)
    ui.fill(stdscr, h - 2, 0, w, " ", attr)
    name = Path(filename).stem.upper() if filename else ""
    left = f" {mode:<11}│<C:>│{name:<13}│{info:<20}│"
    ui.put(stdscr, h - 2, 0, left[:w], attr | curses.A_BOLD)
    if flags:
        ui.put(stdscr, h - 2, max(0, w - len(flags) - 2), flags, attr | curses.A_BOLD)


def message(stdscr, text="", center=True, error=False):
    h, w = stdscr.getmaxyx()
    ui.fill(stdscr, h - 1, 0, w, " ")
    if not text:
        return
    attr = curses.color_pair(ui.C_ERROR) | curses.A_BOLD if error else curses.A_BOLD
    x = max(0, (w - len(text)) // 2) if center else 1
    ui.put(stdscr, h - 1, x, text[:w - 1], attr)


def flags_text(insert=False, deleted=False):
    parts = []
    if deleted:
        parts.append("Del")
    if insert:
        parts.append("Ins")
    return "  ".join(parts)


def ask_yn(stdscr, read_key, text):
    """Pergunta (Y/N) na linha de mensagens, como no FoxBASE+."""
    message(stdscr, text)
    curses.curs_set(0)
    stdscr.refresh()
    while True:
        ch = read_key(stdscr)
        if isinstance(ch, str) and ch.upper() in ("Y", "S"):
            return True
        if isinstance(ch, str) and ch.upper() == "N":
            return False
        if ch == 27:
            return False


def wait_enter(stdscr, read_key, text):
    """'Press ENTER to confirm. Any other key to resume' -> True se Enter."""
    message(stdscr, text)
    curses.curs_set(0)
    stdscr.refresh()
    ch = None
    while ch is None or ch == curses.KEY_RESIZE:
        ch = read_key(stdscr)
    return ch in (10, 13, curses.KEY_ENTER)
