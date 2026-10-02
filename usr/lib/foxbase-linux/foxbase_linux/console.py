"""Tela de comandos (ponto) do FoxBASE+.

A saída rola de baixo para cima: o ponto do prompt fica sempre na linha logo
acima da barra de status. Depois de Enter o cursor volta à coluna 0 da linha do
comando; '?' começa com quebra de linha e '??' escreve onde o cursor está —
por isso '?? "abc"' sobrescreve o início da linha do comando, como no original.
"""

import curses

from . import screen, ui


class Console:
    def __init__(self, app):
        self.app = app
        self.lines = [""]
        self.col = 0
        self.page_lines = None  # contagem para "Press any key to continue..."

    @property
    def width(self):
        return max(20, self.app.stdscr.getmaxyx()[1])

    def rows(self):
        h, _ = self.app.stdscr.getmaxyx()
        return max(1, h - 3 - self.app.top_row())

    # ---------------------------------------------------------- saída
    def clear(self):
        self.lines = [""]
        self.col = 0
        self.just_returned = True

    def out(self, text):
        for ch in str(text):
            if ch == "\n":
                self._newline()
                continue
            if self.col >= self.width:
                self._newline()
            line = self.lines[-1]
            if len(line) < self.col:
                line = line.ljust(self.col)
            self.lines[-1] = line[:self.col] + ch + line[self.col + 1:]
            self.col += 1
        self.lines = self.lines[-2000:]

    def _newline(self):
        self.lines.append("")
        self.col = 0
        if self.page_lines is not None:
            self.page_lines += 1
            if self.page_lines >= self.rows() - 1:
                self._page_pause()

    def _page_pause(self):
        """Tela cheia em DISPLAY ALL / STATUS / MEMORY: espera uma tecla."""
        from .widgets import read_key
        self.lines[-1] = "Press any key to continue..."
        self.col = len(self.lines[-1])
        self.app.draw()
        ch = None
        while ch is None or ch == curses.KEY_RESIZE:
            ch = read_key(self.app.stdscr)
        self.lines = [""]
        self.col = 0
        self.page_lines = 0

    def println(self, text=""):
        """Mensagem em linha própria (como as do original): '\\n' + texto."""
        self.out("\n" + text)

    def write(self, text=""):
        """Compatibilidade: cada linha do texto em linha nova."""
        for line in str(text).split("\n"):
            self.println(line)

    def prompt(self):
        """'\\n. ' — o ponto do prompt sempre em linha nova."""
        if getattr(self, "just_returned", False):
            self.just_returned = False
            self.out(". ")
        elif self.lines == [""] and self.col == 0:
            self.out(". ")
        else:
            self.out("\n. ")

    # ------------------------------------------------------------ tela
    def draw(self, stdscr, edit=None):
        """Desenha a área de saída; com edit (LineEdit) mostra o comando sendo
        digitado após o ponto. Retorna (y, x) do cursor."""
        h, w = stdscr.getmaxyx()
        top = self.app.top_row()
        bottom = h - 4
        lines = list(self.lines)
        cur_col = self.col
        if edit is not None:
            base = lines[-1][:self.col]
            avail = max(1, w - len(base) - 1)
            if edit.pos < edit.scroll:
                edit.scroll = edit.pos
            elif edit.pos >= edit.scroll + avail:
                edit.scroll = edit.pos - avail + 1
            lines[-1] = base + edit.text[edit.scroll:edit.scroll + avail]
            cur_col = len(base) + edit.pos - edit.scroll
        visible = lines[-(bottom - top + 1):]
        start = bottom - len(visible) + 1
        for i, line in enumerate(visible):
            ui.put(stdscr, start + i, 0, line[:w])
        return bottom, min(cur_col, w - 1)

    def read_line(self, label, maxlen=None):
        """Lê uma resposta na própria linha (ex.: 'Enter file name: ')."""
        from .widgets import LineEdit, read_key
        self.out(label)
        edit = LineEdit("", maxlen)
        while True:
            self.app.draw(edit=edit)
            ch = read_key(self.app.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            result = edit.key(ch)
            if result == "enter":
                self.out(edit.text)
                return edit.text
            if result == "cancel":
                return None

    def ask_yn(self, label):
        """Pergunta (Y/N) na linha de comandos; repete até Y ou N."""
        from .widgets import read_key
        self.out(label)
        while True:
            self.app.draw()
            ch = read_key(self.app.stdscr)
            if isinstance(ch, str) and ch.upper() in ("Y", "N"):
                self.out("Yes" if ch.upper() == "Y" else "No")
                return ch.upper() == "Y"
            if ch == 27:
                return False

    def wait(self, label=screen.MSG_ANY_KEY):
        from .widgets import read_key
        self.println(label)
        self.app.draw()
        ch = None
        while ch is None or ch == curses.KEY_RESIZE:
            ch = read_key(self.app.stdscr)
        return ch
