"""Widgets modais: leitura de teclas, campo de edição, diálogos, editor de registro."""

import curses

from . import ui
from .dbf import DBFError


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
    "[Z": curses.KEY_BTAB,
}


def _read_escape(stdscr):
    """ESC sozinho = 27; ESC + sequência conhecida = tecla especial."""
    stdscr.nodelay(True)
    seq = ""
    try:
        while len(seq) < 6:
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


def message(stdscr, text, title="FoxBASE+", error=False):
    h, w = stdscr.getmaxyx()
    lines = str(text).splitlines() or [""]
    width = min(w - 4, max(34, max(len(line) for line in lines) + 6))
    height = min(h - 2, len(lines) + 4)
    y = max(0, (h - height) // 2)
    x = max(0, (w - width) // 2)

    attr = curses.color_pair(ui.C_ERROR) if error else None
    ui.box(stdscr, y, x, height, width, title, attr=attr, clear=True)
    for row, line in enumerate(lines[:height - 4]):
        ui.put(stdscr, y + 1 + row, x + 3, line[:width - 6])
    hint = " Press any key "
    ui.put(stdscr, y + height - 2, x + (width - len(hint)) // 2, hint,
           curses.color_pair(ui.C_REVERSE))
    curses.curs_set(0)
    stdscr.refresh()
    while read_key(stdscr) in (None, curses.KEY_RESIZE):
        pass


def prompt(stdscr, label, default="", title="FoxBASE+", maxlen=None):
    """Caixa de diálogo com um campo. Retorna str ou None (Esc)."""
    h, w = stdscr.getmaxyx()
    width = min(w - 4, max(56, len(label) + 6))
    y = max(0, h // 2 - 3)
    x = max(0, (w - width) // 2)
    ui.box(stdscr, y, x, 6, width, title, clear=True)
    ui.put(stdscr, y + 1, x + 3, label[:width - 6])
    ui.put(stdscr, y + 4, x + 3, "Enter OK   Esc Cancel",
           curses.color_pair(ui.C_DISABLED))
    return line_input(stdscr, y + 2, x + 3, width - 6, default, maxlen)


def confirm(stdscr, text, title="FoxBASE+"):
    h, w = stdscr.getmaxyx()
    width = min(w - 4, max(40, len(text) + 6))
    y = max(0, h // 2 - 3)
    x = max(0, (w - width) // 2)
    ui.box(stdscr, y, x, 5, width, title, clear=True)
    ui.put(stdscr, y + 1, x + 3, text[:width - 6])
    ui.put(stdscr, y + 3, x + 3, "(Y/N)?", curses.color_pair(ui.C_REVERSE))
    curses.curs_set(0)
    stdscr.refresh()
    while True:
        ch = read_key(stdscr)
        if isinstance(ch, str) and ch.upper() in ("Y", "S"):
            return True
        if ch == 27 or (isinstance(ch, str) and ch.upper() == "N"):
            return False


def record_editor(stdscr, dbf, index, title):
    """Tela EDIT de um registro. Retorna True se gravou."""
    values = list(dbf.records[index]["values"])
    field_index = 0
    top = 0
    changed = False
    error = ""

    while True:
        h, w = stdscr.getmaxyx()
        name_w = 11
        val_w = max(dbf.display_width(f) for f in dbf.fields)
        width = min(w - 2, max(64, name_w + val_w + 12))
        height = min(h - 2, len(dbf.fields) + 5)
        y = max(1, (h - height) // 2)
        x = max(0, (w - width) // 2)
        rows = height - 5
        field_w = width - name_w - 8

        if field_index < top:
            top = field_index
        elif field_index >= top + rows:
            top = field_index - rows + 1

        deleted = " *DEL*" if dbf.records[index]["deleted"] else ""
        ui.box(stdscr, y, x, height, width,
               f"{title}  Rec {index + 1}/{dbf.record_count}{deleted}", clear=True)

        for row in range(rows):
            fi = top + row
            if fi >= len(dbf.fields):
                break
            field = dbf.fields[fi]
            shown = dbf.display_value(field, values[fi])
            fw = min(dbf.display_width(field), field_w)
            name_attr = curses.A_BOLD if fi == field_index else 0
            ui.put(stdscr, y + 1 + row, x + 2, f"{field['name']:<{name_w}}", name_attr)
            ui.put(stdscr, y + 1 + row, x + 3 + name_w, field["type"],
                   curses.color_pair(ui.C_DISABLED))
            ui.put(stdscr, y + 1 + row, x + 5 + name_w, shown[:fw].ljust(fw),
                   curses.color_pair(ui.C_REVERSE) if fi == field_index
                   else curses.A_UNDERLINE)

        if error:
            ui.put(stdscr, y + height - 3, x + 2, error[:width - 4],
                   curses.color_pair(ui.C_ERROR))
        ui.put(stdscr, y + height - 2, x + 2,
               "Enter edit  ↑↓ field  PgUp/PgDn rec  Ctrl-W save  Esc cancel"[:width - 4],
               curses.color_pair(ui.C_DISABLED))

        curses.curs_set(0)
        stdscr.refresh()
        ch = read_key(stdscr)
        if ch is None or ch == curses.KEY_RESIZE:
            continue

        if ch == 27:
            if changed and confirm(stdscr, "Discard changes?") is False:
                continue
            return False

        if ch in (curses.KEY_UP, curses.KEY_BTAB):
            field_index = max(0, field_index - 1)
        elif ch in (curses.KEY_DOWN, 9):
            field_index = min(len(dbf.fields) - 1, field_index + 1)
        elif ch == curses.KEY_HOME:
            field_index = 0
        elif ch == curses.KEY_END:
            field_index = len(dbf.fields) - 1
        elif ch in (23, curses.KEY_F2):  # Ctrl-W / F2
            dbf.records[index]["values"] = values
            dbf.save()
            return True
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            if changed:
                dbf.records[index]["values"] = values
                dbf.save()
            step = -1 if ch == curses.KEY_PPAGE else 1
            new_index = index + step
            if 0 <= new_index < dbf.record_count:
                index = new_index
                values = list(dbf.records[index]["values"])
                changed = False
            error = ""
        elif is_enter(ch) or isinstance(ch, str):
            field = dbf.fields[field_index]
            if field["type"] not in ("C", "N", "F", "D", "L"):
                error = f"{field['name']}: memo/binary fields are read-only."
                continue
            row = field_index - top
            current = dbf.display_value(field, values[field_index]).rstrip()
            if field["type"] == "D" and not values[field_index]:
                current = ""
            if field["type"] == "L" and current == "?":
                current = ""
            if isinstance(ch, str):  # começa a digitar direto substituindo
                current = ch
            fw = min(dbf.display_width(field), field_w)
            text = line_input(stdscr, y + 1 + row, x + 5 + name_w, fw,
                              current, maxlen=dbf.display_width(field))
            if text is None:
                continue
            try:
                values[field_index] = dbf.validate(field, text)
                changed = True
                error = ""
                field_index = min(len(dbf.fields) - 1, field_index + 1)
            except DBFError as exc:
                error = str(exc)
