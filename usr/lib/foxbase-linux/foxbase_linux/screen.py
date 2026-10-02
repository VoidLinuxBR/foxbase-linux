"""Partes comuns das telas, reproduzindo o FoxBASE+ 2.10.

Tela de 25 linhas do original (as posições são relativas ao fim da tela):
    linha h-3  barra de status ("BROWSE ║<C:>║CLIENTES ║Rec: 1/6 ║ ║")
    linha h-2  mensagem / pergunta
    linha h-1  mensagem de ajuda da tela ("View and edit fields.")
A caixa de navegação (F1 liga/desliga) fica no topo, como no original.
"""

import curses
from pathlib import Path

from . import ui

HELP_BROWSE = (
    "╔══════════════════╦═════════════════════╦══════════════╦════════════════════╗",
    "║ CURSOR  <-- -->  ║         UP   DOWN   ║    DELETE    ║ Insert Mode:  Ins  ║",
    "║  Char:    ←  →   ║ Record:  ↑     ↓    ║ Char:  Del   ║ Exit:        ^End  ║",
    "║  Word:  Home End ║ Page:  PgUp  PgDn   ║ Field:  ^Y   ║ Abort:        Esc  ║",
    "║  Pan:    ^← ^→   ║ Help:   F1          ║ Record: ^U   ║ Set Options: ^Home ║",
    "╚══════════════════╩═════════════════════╩══════════════╩════════════════════╝",
)

HELP_EDIT = (
    "╔══════════════════╦═════════════════════╦══════════════╦════════════════════╗",
    "║ CURSOR  <-- -->  ║         UP   DOWN   ║    DELETE    ║ Insert Mode:  Ins  ║",
    "║  Char:    ←  →   ║ Field:   ↑     ↓    ║ Char:  Del   ║ Exit:        ^End  ║",
    "║  Word:  Home End ║ Page:  PgUp  PgDn   ║ Field:  ^Y   ║ Abort:        Esc  ║",
    "║                  ║ Help:   F1          ║ Record: ^U   ║ Memo:        ^Home ║",
    "╚══════════════════╩═════════════════════╩══════════════╩════════════════════╝",
)

HELP_CREATE = (
    "╔══════════════════╦══════════════╦══════════════╦═════════════════════╗",
    "║ CURSOR  <-- -->  ║    INSERT    ║    DELETE    ║ Up/Down Field: ↑ ↓  ║",
    "║  Char:    ←  →   ║  Char:  Ins  ║  Char:  Del  ║ Cursor Menu:  ^Home ║",
    "║  Word:  Home End ║  Field:  ^N  ║  Word:   ^Y  ║ Exit/Save:    ^End  ║",
    "║  Pan:    ^← ^→   ║  Help:   F1  ║  Field:  ^U  ║ Abort:         Esc  ║",
    "╚══════════════════╩══════════════╩══════════════╩═════════════════════╝",
)

HELP_MODIFY_COMMAND = (
    "╔══════════════════╦═════════════════════╦══════════════╦════════════════════╗",
    "║ CURSOR  <-- -->  ║         UP   DOWN   ║    DELETE    ║ Insert Mode:  Ins  ║",
    "║  Char:    ←  →   ║ Field:   ↑     ↓    ║ Char:  Del   ║ Insert line:  ^N   ║",
    "║  Word:  Home End ║ Page:  PgUp  PgDn   ║ Word:   ^T   ║ Save: ^W  Abort:Esc║",
    "║  Line:   ^← ^→   ║ Find:   ^KF         ║ Line:   ^Y   ║ Readfile:    ^KR   ║",
    "║  Reformat: ^KB   ║ Refind: ^KL         ║              ║ Writefile:   ^KW   ║",
    "╚══════════════════╩═════════════════════╩══════════════╩════════════════════╝",
)

MSG_SELECT = "Position selection bar with ←→.  Select ◄┘."
MSG_SELECT_DASH = "Position selection bar with ←→.  Select - ◄┘."
MSG_ANY_KEY = "Press any key to continue ..."
MSG_ABANDON = "Are you sure you want to abandon the operation? (Y/N) "


def clear(stdscr):
    ui.clear(stdscr)


def help_box(stdscr, lines, y=1, x=0):
    """Desenha a caixa de navegação; retorna a linha logo abaixo dela."""
    attr = curses.color_pair(ui.C_BORDER)
    for row, text in enumerate(lines):
        ui.put(stdscr, y + row, x, text, attr)
    return y + len(lines)


def status_bar(stdscr, mode, filename="", info="", flags=""):
    """Barra de status do original: modo │<C:>│arquivo│registro│Ins/Del│"""
    h, w = stdscr.getmaxyx()
    attr = curses.color_pair(ui.C_REVERSE)
    name = Path(filename).stem.upper() if filename else ""
    text = (f"{mode[:16]:<16}║<C:>║{name[:23]:<23}║{info[:19]:<19}║"
            f"{flags[-6:]:>6}║")
    ui.fill(stdscr, h - 3, 0, w, " ", attr)
    ui.put(stdscr, h - 3, 0, text, attr)


def message(stdscr, text="", row=2, error=False):
    """Mensagem centralizada; row=2 -> linha h-2, row=1 -> linha h-1."""
    h, w = stdscr.getmaxyx()
    y = h - row
    ui.fill(stdscr, y, 0, w, " ")
    if text:
        attr = curses.color_pair(ui.C_ERROR) | curses.A_BOLD if error else 0
        ui.put(stdscr, y, max(0, (min(w, 80) - len(text)) // 2), text[:w - 1], attr)


def messages(stdscr, line1="", line2=""):
    message(stdscr, line1, 2)
    message(stdscr, line2, 1)


def flags_text(insert=False, deleted=False):
    return ("Ins" if insert else "") + ("Del" if deleted else "")


def wait_key(stdscr, read_key):
    curses.curs_set(0)
    stdscr.refresh()
    ch = None
    while ch is None or ch == curses.KEY_RESIZE:
        ch = read_key(stdscr)
    return ch


def ask_yn(stdscr, read_key, text, row=2):
    """Pergunta (Y/N) na linha de mensagens."""
    message(stdscr, text, row)
    while True:
        ch = wait_key(stdscr, read_key)
        if isinstance(ch, str) and ch.upper() == "Y":
            return True
        if isinstance(ch, str) and ch.upper() == "N":
            return False
        if ch == 27:
            return False


def wait_enter(stdscr, read_key, text, row=2):
    """True se Enter (ex.: 'Press ENTER to confirm.  Any other key to resume.')."""
    message(stdscr, text, row)
    ch = wait_key(stdscr, read_key)
    return ch in (10, 13, curses.KEY_ENTER)


def error_wait(stdscr, read_key, text):
    """Erro na linha h-2 e 'Press any key to continue ...' na h-1."""
    curses.beep()
    messages(stdscr, text, MSG_ANY_KEY)
    wait_key(stdscr, read_key)


class OptionBar:
    """Barra de opções de uma linha (menu do BROWSE e do CREATE), com a
    aparência da barra de menus do foxbase-linux e as opções do original.

    items: [(rótulo, mensagem da linha h-1), ...]; positions: coluna de cada um.
    """

    def __init__(self, items, positions, select_msg=MSG_SELECT):
        self.items = items
        self.positions = positions
        self.select_msg = select_msg
        self.index = 0

    def draw(self, stdscr):
        _, w = stdscr.getmaxyx()
        ui.fill(stdscr, 0, 0, w, " ", curses.color_pair(ui.C_MENU))
        for i, ((label, _), x) in enumerate(zip(self.items, self.positions)):
            if i == self.index:
                ui.put(stdscr, 0, x, label, curses.color_pair(ui.C_REVERSE) | curses.A_BOLD)
                continue
            hot = next((c for c in label if c.isupper()), label[0])
            pos = label.index(hot)
            ui.put(stdscr, 0, x, label, curses.color_pair(ui.C_MENU))
            ui.put(stdscr, 0, x + pos, hot, curses.color_pair(ui.C_HOTKEY) | curses.A_BOLD)
        messages(stdscr, self.select_msg, self.items[self.index][1])

    def key(self, ch):
        """Retorna o índice escolhido, -1 para sair, ou None."""
        if ch in (27, curses.KEY_F10):
            return -1
        if ch == curses.KEY_LEFT:
            self.index = (self.index - 1) % len(self.items)
        elif ch == curses.KEY_RIGHT:
            self.index = (self.index + 1) % len(self.items)
        elif ch in (10, 13, curses.KEY_ENTER):
            return self.index
        elif isinstance(ch, str):
            for i, (label, _) in enumerate(self.items):
                hot = next((c for c in label if c.isupper()), label[0])
                if hot.upper() == ch.upper():
                    self.index = i
                    return i
        return None


def popup_input(stdscr, read_key, x, label, default="", width=34, y=2):
    """Caixa 'Enter new record #: ' abaixo da opção do menu. None = Esc."""
    from .widgets import line_input
    _, w = stdscr.getmaxyx()
    x = max(0, min(x, w - width))
    ui.box(stdscr, y, x, 3, width, attr=curses.color_pair(ui.C_BORDER), clear=True,
           double=True)
    ui.put(stdscr, y + 1, x + 2, label)
    field_x = x + 2 + len(label)
    return line_input(stdscr, y + 1, field_x, max(1, x + width - 2 - field_x), default)
