"""MODIFY COMMAND: editor de programas .prg."""

import curses
import tempfile
from pathlib import Path

from . import runner, ui
from .widgets import is_backspace, is_enter


DEFAULT_PROGRAM = [
    "* Programa FoxBASE+/Harbour",
    "PROCEDURE Main",
    "   CLS",
    "   ? 'Hello from Harbour'",
    "   ? 'Data: ', DATE()",
    "   WAIT",
    "RETURN",
]


class Editor:
    def __init__(self, app):
        self.app = app
        self.lines = list(DEFAULT_PROGRAM)
        self.filename = None
        self.modified = False
        self.row = 0
        self.col = 0
        self.scroll = 0
        self.hscroll = 0

    # ------------------------------------------------------------ arquivo
    @property
    def title(self):
        name = self.filename.name if self.filename else "UNTITLED.PRG"
        return f"Modify Command: {name}{' *' if self.modified else ''}"

    def load(self, filename):
        path = Path(filename).expanduser()
        if not path.suffix:
            path = path.with_suffix(".prg")
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            self.lines = text.replace("\r\n", "\n").replace("\t", "   ").split("\n")
            if len(self.lines) > 1 and self.lines[-1] == "":
                self.lines.pop()
            self.lines = self.lines or [""]
            self.app.status = f"{path.name} loaded."
        else:
            self.lines = [""]
            self.app.status = f"New file {path.name}."
        self.filename = path.resolve()
        self.modified = False
        self.row = self.col = self.scroll = self.hscroll = 0

    def save(self, ask=True):
        if not self.filename:
            if not ask:
                return False
            name = self.app.ask("Save program as:", "program.prg")
            if not name:
                return False
            path = Path(name).expanduser()
            if not path.suffix:
                path = path.with_suffix(".prg")
            self.filename = path.resolve()
        try:
            self.filename.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError as exc:
            self.app.error(f"Cannot save: {exc}")
            return False
        self.modified = False
        self.app.status = f"{self.filename.name} saved."
        return True

    def run(self):
        if self.filename:
            if self.modified and not self.save():
                return
            self.app.show_command()
            runner.compile_and_run(self.app, self.filename)
            return
        # sem nome: compila uma cópia temporária
        self.app.show_command()
        with tempfile.TemporaryDirectory(prefix="foxbase-src-") as tmp:
            src = Path(tmp) / "untitled.prg"
            src.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
            runner.compile_and_run(self.app, src)

    # ------------------------------------------------------------- tela
    def draw(self, stdscr):
        """Desenha o conteúdo e retorna (y, x) do cursor."""
        h, w = stdscr.getmaxyx()
        top, left = 2, 2
        height = h - 5
        gutter = 5
        text_w = w - left - gutter - 2

        if self.row < self.scroll:
            self.scroll = self.row
        elif self.row >= self.scroll + height:
            self.scroll = self.row - height + 1
        if self.col < self.hscroll:
            self.hscroll = self.col
        elif self.col >= self.hscroll + text_w:
            self.hscroll = self.col - text_w + 1

        for line_no in range(height):
            index = self.scroll + line_no
            if index >= len(self.lines):
                break
            ui.put(stdscr, top + line_no, left, f"{index + 1:4d} ",
                   curses.color_pair(ui.C_DISABLED))
            ui.put(stdscr, top + line_no, left + gutter,
                   self.lines[index][self.hscroll:self.hscroll + text_w])

        info = f" Line {self.row + 1}  Col {self.col + 1} "
        ui.put(stdscr, h - 3, left,
               "F2 Save  F5 Run  Ctrl-Y Del line  Esc Command",
               curses.color_pair(ui.C_DISABLED))
        ui.put(stdscr, h - 3, w - len(info) - 3, info, curses.color_pair(ui.C_DISABLED))

        return top + self.row - self.scroll, left + gutter + self.col - self.hscroll

    # ----------------------------------------------------------- teclas
    def _clamp_col(self):
        self.col = min(self.col, len(self.lines[self.row]))

    def key(self, ch):
        if ch == 27:
            self.app.show_command()
            return
        if ch in (curses.KEY_F2, 23):  # F2 / Ctrl-W
            self.save()
            return
        if ch == curses.KEY_F5:
            self.run()
            return

        page = max(1, self.app.stdscr.getmaxyx()[0] - 6)
        line = self.lines[self.row]

        if ch == curses.KEY_UP:
            self.row = max(0, self.row - 1)
            self._clamp_col()
        elif ch == curses.KEY_DOWN:
            self.row = min(len(self.lines) - 1, self.row + 1)
            self._clamp_col()
        elif ch == curses.KEY_PPAGE:
            self.row = max(0, self.row - page)
            self._clamp_col()
        elif ch == curses.KEY_NPAGE:
            self.row = min(len(self.lines) - 1, self.row + page)
            self._clamp_col()
        elif ch == curses.KEY_LEFT:
            if self.col:
                self.col -= 1
            elif self.row:
                self.row -= 1
                self.col = len(self.lines[self.row])
        elif ch == curses.KEY_RIGHT:
            if self.col < len(line):
                self.col += 1
            elif self.row < len(self.lines) - 1:
                self.row += 1
                self.col = 0
        elif ch == curses.KEY_HOME:
            self.col = 0
        elif ch == curses.KEY_END:
            self.col = len(line)
        elif ch == 543 or ch == 535:  # Ctrl-Home (xterm) - início do arquivo
            self.row = self.col = 0
        elif is_backspace(ch):
            if self.col:
                self.lines[self.row] = line[:self.col - 1] + line[self.col:]
                self.col -= 1
            elif self.row:
                prev = self.lines[self.row - 1]
                self.lines[self.row - 1] = prev + line
                del self.lines[self.row]
                self.row -= 1
                self.col = len(prev)
            self.modified = True
        elif ch == curses.KEY_DC:
            if self.col < len(line):
                self.lines[self.row] = line[:self.col] + line[self.col + 1:]
            elif self.row < len(self.lines) - 1:
                self.lines[self.row] = line + self.lines.pop(self.row + 1)
            self.modified = True
        elif ch == 25:  # Ctrl-Y
            if len(self.lines) > 1:
                del self.lines[self.row]
                self.row = min(self.row, len(self.lines) - 1)
            else:
                self.lines = [""]
            self.col = 0
            self.modified = True
        elif is_enter(ch):
            indent = len(line) - len(line.lstrip(" "))
            indent = min(indent, self.col)
            self.lines[self.row] = line[:self.col]
            self.lines.insert(self.row + 1, " " * indent + line[self.col:])
            self.row += 1
            self.col = indent
            self.modified = True
        elif ch == 9:  # Tab
            self.lines[self.row] = line[:self.col] + "   " + line[self.col:]
            self.col += 3
            self.modified = True
        elif isinstance(ch, str):
            self.lines[self.row] = line[:self.col] + ch + line[self.col:]
            self.col += 1
            self.modified = True
