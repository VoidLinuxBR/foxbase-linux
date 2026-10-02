"""Widgets modais: leitura de teclas, campo de edição e diálogos."""

import curses

from . import ui


# Teclas com Ctrl que o curses não tem como constante própria
CTRL_END = 0x10001
CTRL_HOME = 0x10002
CTRL_LEFT = 0x10003
CTRL_RIGHT = 0x10004
CTRL_PGUP = 0x10005
CTRL_PGDN = 0x10006
ALT_BASE = 0x20000

KEYNAMES = {
    b"kEND5": CTRL_END, b"kHOM5": CTRL_HOME,
    b"kLFT5": CTRL_LEFT, b"kRIT5": CTRL_RIGHT,
    b"kPRV5": CTRL_PGUP, b"kNXT5": CTRL_PGDN,
}


def read_key(stdscr):
    """Lê uma tecla com suporte a UTF-8.

    Retorna int para teclas especiais/controle (KEY_*, 10, 27, 127...)
    e str de 1 caractere para texto imprimível.
    """
    try:
        ch = stdscr.get_wch()
    except curses.error:
        return None
    except KeyboardInterrupt:
        return 3
    if isinstance(ch, str):
        code = ord(ch)
        if code == 27:
            return _read_escape(stdscr)
        if code < 32 or code == 127:
            return code
        return ch
    if isinstance(ch, int) and ch > 255:
        try:
            return KEYNAMES.get(curses.keyname(ch), ch)
        except ValueError:
            return ch
    return ch


# Sequências que alguns terminais mandam mesmo fora do terminfo
ESCAPE_KEYS = {
    "[A": curses.KEY_UP, "[B": curses.KEY_DOWN,
    "[C": curses.KEY_RIGHT, "[D": curses.KEY_LEFT,
    "OA": curses.KEY_UP, "OB": curses.KEY_DOWN,
    "OC": curses.KEY_RIGHT, "OD": curses.KEY_LEFT,
    "[H": curses.KEY_HOME, "[F": curses.KEY_END,
    "OH": curses.KEY_HOME, "OF": curses.KEY_END,
    "[1~": curses.KEY_HOME, "[4~": curses.KEY_END,
    "[7~": curses.KEY_HOME, "[8~": curses.KEY_END,
    "[2~": curses.KEY_IC, "[3~": curses.KEY_DC,
    "[5~": curses.KEY_PPAGE, "[6~": curses.KEY_NPAGE,
    "OP": curses.KEY_F1, "OQ": curses.KEY_F2,
    "OR": curses.KEY_F3, "OS": curses.KEY_F4,
    "[11~": curses.KEY_F1, "[12~": curses.KEY_F2,
    "[13~": curses.KEY_F3, "[14~": curses.KEY_F4,
    "[15~": curses.KEY_F5, "[17~": curses.KEY_F6,
    "[18~": curses.KEY_F7, "[19~": curses.KEY_F8,
    "[20~": curses.KEY_F9, "[21~": curses.KEY_F10,
    "[23~": curses.KEY_F11, "[24~": curses.KEY_F12,
    "[Z": curses.KEY_BTAB,
    "[1;5F": CTRL_END, "[4;5~": CTRL_END, "[8^": CTRL_END, "[4^": CTRL_END,
    "[1;5H": CTRL_HOME, "[1;5~": CTRL_HOME, "[7^": CTRL_HOME,
    "[1;5D": CTRL_LEFT, "[1;5C": CTRL_RIGHT, "Od": CTRL_LEFT, "Oc": CTRL_RIGHT,
    "[5;5~": CTRL_PGUP, "[6;5~": CTRL_PGDN,
}


def _read_escape(stdscr):
    """ESC sozinho = 27; ESC + sequência conhecida = tecla especial."""
    stdscr.nodelay(True)
    seq = ""
    try:
        while len(seq) < 7:
            try:
                ch = stdscr.get_wch()
            except curses.error:
                break
            if not isinstance(ch, str):
                break
            seq += ch
            if seq in ESCAPE_KEYS:
                return ESCAPE_KEYS[seq]
            if len(seq) >= 2 and (ch.isalpha() or ch == "~"):
                return None  # sequência desconhecida: ignora
    finally:
        stdscr.nodelay(False)
    if not seq:
        return 27
    if len(seq) == 1 and seq.isalpha():
        return ALT_BASE + ord(seq.lower())  # Alt+letra
    return None


def is_enter(ch):
    return ch in (10, 13, curses.KEY_ENTER)


def is_backspace(ch):
    return ch in (curses.KEY_BACKSPACE, 8, 127)


class LineEdit:
    """Linha editável com cursor, Home/End, Del, Backspace e rolagem horizontal."""

    def __init__(self, text="", maxlen=None):
        self.text = text
        self.maxlen = maxlen
        self.pos = len(text)
        self.scroll = 0

    def set(self, text):
        self.text = text
        self.pos = len(text)
        self.scroll = 0

    def key(self, ch):
        """Retorna 'enter', 'cancel' ou None (tecla consumida/ignorada)."""
        if is_enter(ch):
            return "enter"
        if ch == 27:
            return "cancel"
        if ch == curses.KEY_LEFT:
            self.pos = max(0, self.pos - 1)
        elif ch == curses.KEY_RIGHT:
            self.pos = min(len(self.text), self.pos + 1)
        elif ch in (curses.KEY_HOME, 1):  # Ctrl-A
            self.pos = 0
        elif ch in (curses.KEY_END, 5):  # Ctrl-E
            self.pos = len(self.text)
        elif is_backspace(ch):
            if self.pos:
                self.text = self.text[:self.pos - 1] + self.text[self.pos:]
                self.pos -= 1
        elif ch in (curses.KEY_DC, 7):  # Del / Ctrl-G
            self.text = self.text[:self.pos] + self.text[self.pos + 1:]
        elif ch == 25:  # Ctrl-Y apaga a linha
            self.set("")
        elif ch == 11:  # Ctrl-K apaga até o fim
            self.text = self.text[:self.pos]
        elif isinstance(ch, str):
            if self.maxlen is None or len(self.text) < self.maxlen:
                self.text = self.text[:self.pos] + ch + self.text[self.pos:]
                self.pos += 1
        return None

    def draw(self, stdscr, y, x, width, attr=0):
        """Desenha e retorna a coluna do cursor na tela."""
        width = max(1, width)
        if self.pos < self.scroll:
            self.scroll = self.pos
        elif self.pos >= self.scroll + width:
            self.scroll = self.pos - width + 1
        visible = self.text[self.scroll:self.scroll + width]
        ui.put(stdscr, y, x, visible.ljust(width), attr)
        return x + self.pos - self.scroll


def line_input(stdscr, y, x, width, text="", maxlen=None, attr=None):
    """Campo modal. Retorna o texto (Enter) ou None (Esc)."""
    attr = curses.color_pair(ui.C_REVERSE) if attr is None else attr
    edit = LineEdit(text, maxlen)
    curses.curs_set(1)
    while True:
        cx = edit.draw(stdscr, y, x, width, attr)
        try:
            stdscr.move(y, cx)
        except curses.error:
            pass
        stdscr.refresh()
        ch = read_key(stdscr)
        if ch is None or ch == curses.KEY_RESIZE:
            continue
        result = edit.key(ch)
        if result == "enter":
            return edit.text
        if result == "cancel":
            return None
