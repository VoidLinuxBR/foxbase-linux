"""MODIFY COMMAND (e edição de campo memo), como no FoxBASE+ 2.10.

Linha 0: "Edit: C:\\ARQUIVO.PRG" (ou a pergunta/entrada do momento), caixa de
navegação (F1 liga/desliga) e o texto ocupando o resto da tela.
^W ou ^End grava e sai; Esc sai (se alterado: "Abort editing? (Y/N): ").
^N insere linha, ^Y apaga linha, ^T apaga palavra, Home/End palavra,
^←/^→ início/fim da linha, ^KF procura, ^KL procura de novo, ^KR lê arquivo,
^KW grava em arquivo, ^KB reformata o parágrafo.
"""

import curses
from pathlib import Path

from . import screen, ui
from .widgets import (CTRL_END, CTRL_HOME, CTRL_LEFT, CTRL_PGDN, CTRL_PGUP, CTRL_RIGHT,
                      LineEdit, is_backspace, is_enter, read_key)

TAB = 8


class TextEditor:
    def __init__(self, app, lines, title):
        self.app = app
        self.stdscr = app.stdscr
        self.lines = lines or [""]
        self.title = title
        self.row = self.col = 0
        self.top = self.left = 0
        self.modified = False
        self.find_text = ""
        self.msg = ""

    # ------------------------------------------------------------- tela
    def text_top(self):
        if self.app.show_help:
            return 1 + len(screen.HELP_MODIFY_COMMAND)
        return 1

    def draw(self, line0=None):
        stdscr = self.stdscr
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        ui.put(stdscr, 0, 0, line0 if line0 is not None else (self.msg or self.title))
        if self.app.show_help:
            screen.help_box(stdscr, screen.HELP_MODIFY_COMMAND, y=1)
        top = self.text_top()
        height = max(1, h - top)
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + height:
            self.top = self.row - height + 1
        if self.col < self.left:
            self.left = self.col
        elif self.col >= self.left + w - 1:
            self.left = self.col - w + 2
        for i in range(height):
            index = self.top + i
            if index >= len(self.lines):
                break
            ui.put(stdscr, top + i, 0, self.lines[index][self.left:self.left + w])
        if line0 is None:
            curses.curs_set(1)
            try:
                stdscr.move(top + self.row - self.top, self.col - self.left)
            except curses.error:
                pass
        stdscr.refresh()

    def ask_line0(self, label):
        """Entrada na linha 0 (procura, nome de arquivo)."""
        edit = LineEdit()
        while True:
            self.draw(label + edit.text)
            curses.curs_set(1)
            try:
                self.stdscr.move(0, len(label) + edit.pos)
            except curses.error:
                pass
            ch = read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            result = edit.key(ch)
            if result == "enter":
                return edit.text
            if result == "cancel":
                return None

    def ask_yn(self, label):
        while True:
            self.draw(label)
            ch = read_key(self.stdscr)
            if isinstance(ch, str) and ch.upper() in ("Y", "N"):
                return ch.upper() == "Y"

    # ----------------------------------------------------------- edição
    def _line(self):
        return self.lines[self.row]

    def _set(self, text):
        self.lines[self.row] = text
        self.modified = True

    def _pad(self):
        line = self._line()
        if len(line) < self.col:
            self.lines[self.row] = line.ljust(self.col)

    def _word_left(self):
        line, col = self._line(), self.col
        while col > 0 and (col > len(line) or line[col - 1] == " "):
            col -= 1
        while col > 0 and line[col - 1] != " ":
            col -= 1
        return col

    def _word_right(self):
        line, col = self._line(), self.col
        while col < len(line) and line[col] != " ":
            col += 1
        while col < len(line) and line[col] == " ":
            col += 1
        return col

    def _find(self, text, start_row, start_col):
        if not text:
            return False
        needle = text.upper()
        for r in range(start_row, len(self.lines)):
            col = self.lines[r].upper().find(needle, start_col if r == start_row else 0)
            if col >= 0:
                self.row, self.col = r, col
                return True
        return False

    def _reformat(self):
        """^KB: junta e quebra o parágrafo na largura do MEMOWIDTH."""
        from . import settings
        width = settings.state["MEMOWIDTH"]
        start = self.row
        end = start
        while end < len(self.lines) and self.lines[end].strip():
            end += 1
        words = " ".join(self.lines[start:end]).split()
        out, line = [], ""
        for word in words:
            if line and len(line) + 1 + len(word) > width:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}" if line else word
        if line:
            out.append(line)
        self.lines[start:end] = out or [""]
        self.modified = True

    def ctrl_k(self):
        self.draw("^K")
        ch = read_key(self.stdscr)
        letter = chr(ch + 64) if isinstance(ch, int) and 0 < ch < 27 else \
            (ch.upper() if isinstance(ch, str) else "")
        if letter == "F":
            text = self.ask_line0("Enter string: ")
            if text:
                self.find_text = text
                if not self._find(text, self.row, self.col + 1):
                    curses.beep()
                    self.msg = "No find."
        elif letter == "L":
            if not self._find(self.find_text, self.row, self.col + 1):
                curses.beep()
                self.msg = "No find."
        elif letter == "R":
            name = self.ask_line0("Enter file name: ")
            if name:
                try:
                    text = Path(name).expanduser().read_text(encoding="utf-8",
                                                             errors="replace")
                except OSError:
                    curses.beep()
                    self.msg = "File does not exist."
                    return
                new = text.replace("\r\n", "\n").replace("\t", " " * TAB).split("\n")
                if new and new[-1] == "":
                    new.pop()
                self.lines[self.row:self.row] = new
                self.modified = True
        elif letter == "W":
            name = self.ask_line0("Enter file name: ")
            if name:
                try:
                    Path(name).expanduser().write_text("\n".join(self.lines) + "\n",
                                                        encoding="utf-8")
                except OSError:
                    curses.beep()
        elif letter == "B":
            self._reformat()

    def run(self):
        """Retorna as linhas gravadas (^W/^End) ou None (Esc)."""
        while True:
            self.draw()
            ch = read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            self.msg = ""
            h, _ = self.stdscr.getmaxyx()
            page = max(1, h - self.text_top() - 1)
            line = self._line()

            if ch in (23, CTRL_END):  # ^W / ^End
                while len(self.lines) > 1 and not self.lines[-1].strip():
                    self.lines.pop()
                return [l.rstrip() for l in self.lines]
            if ch == 27:
                if not self.modified or self.ask_yn("Abort editing? (Y/N): "):
                    return None
                continue
            if ch == curses.KEY_F1:
                self.app.show_help = not self.app.show_help
            elif ch == curses.KEY_IC:
                self.app.insert_mode = not self.app.insert_mode
            elif ch == curses.KEY_UP:
                self.row = max(0, self.row - 1)
            elif ch == curses.KEY_DOWN:
                self.row = min(len(self.lines) - 1, self.row + 1)
            elif ch == curses.KEY_LEFT:
                if self.col:
                    self.col -= 1
                elif self.row:
                    self.row -= 1
                    self.col = len(self.lines[self.row])
            elif ch == curses.KEY_RIGHT:
                self.col += 1
            elif ch == curses.KEY_HOME:
                self.col = self._word_left()
            elif ch == curses.KEY_END:
                self.col = self._word_right()
            elif ch == CTRL_LEFT:
                self.col = 0
            elif ch == CTRL_RIGHT:
                self.col = len(line)
            elif ch == curses.KEY_PPAGE:
                self.row = max(0, self.row - page)
            elif ch == curses.KEY_NPAGE:
                self.row = min(len(self.lines) - 1, self.row + page)
            elif ch in (CTRL_HOME, CTRL_PGUP):
                self.row = self.col = 0
            elif ch == CTRL_PGDN:
                self.row = len(self.lines) - 1
                self.col = len(self.lines[self.row])
            elif ch == 14:  # ^N
                self.lines.insert(self.row, "")
                self.col = 0
                self.modified = True
            elif ch == 25:  # ^Y
                if len(self.lines) > 1:
                    del self.lines[self.row]
                    self.row = min(self.row, len(self.lines) - 1)
                else:
                    self.lines = [""]
                self.modified = True
            elif ch == 20:  # ^T apaga a palavra à direita
                end = self._word_right()
                self._set(line[:self.col] + line[end:])
            elif ch == 11:  # ^K
                self.ctrl_k()
            elif ch == curses.KEY_DC:
                if self.col < len(line):
                    self._set(line[:self.col] + line[self.col + 1:])
                elif self.row < len(self.lines) - 1:
                    self._pad()
                    self._set(self._line() + self.lines.pop(self.row + 1))
            elif is_backspace(ch):
                if self.col:
                    self._pad()
                    line = self._line()
                    self._set(line[:self.col - 1] + line[self.col:])
                    self.col -= 1
                elif self.row:
                    prev = self.lines[self.row - 1]
                    self.lines[self.row - 1] = prev + line
                    del self.lines[self.row]
                    self.row -= 1
                    self.col = len(prev)
                    self.modified = True
            elif is_enter(ch):
                if self.app.insert_mode:
                    self._pad()
                    line = self._line()
                    self._set(line[:self.col])
                    self.lines.insert(self.row + 1, line[self.col:])
                elif self.row == len(self.lines) - 1:
                    self.lines.append("")
                    self.modified = True
                self.row += 1
                self.col = 0
            elif ch == 9:
                self.col = (self.col // TAB + 1) * TAB
            elif isinstance(ch, str):
                self._pad()
                line = self._line()
                if self.app.insert_mode:
                    self._set(line[:self.col] + ch + line[self.col:])
                else:
                    self._set(line[:self.col] + ch + line[self.col + 1:])
                self.col += 1
            self.col = max(0, min(self.col, 253))


def modify_command(app, path):
    path = Path(path)
    lines = [""]
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.replace("\r\n", "\n").replace("\t", " " * TAB).split("\n")
        if len(lines) > 1 and lines[-1] == "":
            lines.pop()
    editor = TextEditor(app, lines, f"Edit: {path}")
    result = editor.run()
    if result is None:
        return False
    backup = path.with_suffix(".bak" if path.suffix.islower() else ".BAK")
    try:
        if path.exists():
            path.replace(backup)
        path.write_text("\n".join(result) + "\n", encoding="utf-8")
    except OSError:
        curses.beep()
        return False
    return True


def edit_memo(app, text, field_name):
    lines = text.split("\n") if text else [""]
    editor = TextEditor(app, lines, f"Edit: {field_name}")
    result = editor.run()
    if result is None:
        return None
    return "\n".join(result).rstrip()
