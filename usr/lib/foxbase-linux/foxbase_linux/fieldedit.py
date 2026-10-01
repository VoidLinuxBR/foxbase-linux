"""Edição de um campo em tela cheia, no estilo dBASE III PLUS / FoxBASE+.

Cada campo tem largura fixa: digitar sobrescreve (ou insere, com Ins), ao encher
o campo o cursor passa sozinho para o próximo (com bipe), a data tem as barras
fixas e o número é alinhado à direita ao sair do campo.
"""

import curses

from . import ui
from .dbf import DBFError
from .widgets import is_backspace

EDITABLE = ("C", "N", "F", "D", "L")
DATE_BLANK = "  /  /    "
DATE_SEPARATORS = (2, 5)


class FieldEditor:
    def __init__(self, dbf, field, raw):
        self.dbf = dbf
        self.field = field
        self.kind = field["type"]
        self.width = dbf.display_width(field)
        self.editable = self.kind in EDITABLE
        self.text = self._to_text(raw)
        self.pos = self._fix(0, 1)
        self.dirty = False
        self.hscroll = 0

    # ------------------------------------------------------------ valor
    def _to_text(self, raw):
        kind = self.kind
        if kind == "C":
            return raw[:self.width].ljust(self.width)
        if kind in ("N", "F"):
            return raw.strip()[:self.width].rjust(self.width)
        if kind == "D":
            shown = self.dbf.display_value(self.field, raw)
            return shown if shown.strip("/ ") else DATE_BLANK
        if kind == "L":
            value = raw.strip()[:1].upper()
            return value if value in ("T", "F", "Y", "N") else " "
        return self.dbf.display_value(self.field, raw)[:self.width].ljust(self.width)

    def is_blank(self):
        return not self.text.replace("/", "").strip()

    def value(self):
        """Valor cru para gravar (levanta DBFError se inválido)."""
        if not self.editable:
            raise DBFError("read-only")
        if self.kind == "D" and self.is_blank():
            return ""
        return self.dbf.validate(self.field, self.text)

    def normalize(self):
        """Ao sair do campo: valida e reformata (número à direita etc.)."""
        if not self.editable:
            return
        raw = self.value()
        self.text = self._to_text(raw)
        self.pos = self._fix(0, 1)

    # ----------------------------------------------------------- cursor
    def _fix(self, pos, step):
        """Pula as barras fixas da data."""
        if self.kind == "D":
            while pos in DATE_SEPARATORS:
                pos += step
        return max(0, min(pos, self.width - 1))

    def home(self):
        self.pos = self._fix(0, 1)

    def end(self):
        stripped = len(self.text.rstrip())
        self.pos = self._fix(min(stripped, self.width - 1), -1)

    def _allowed(self, ch):
        if self.kind == "C":
            return True
        if self.kind in ("N", "F"):
            return ch.isdigit() or ch in ".- "
        if self.kind == "D":
            return ch.isdigit() or ch == " "
        if self.kind == "L":
            return ch.upper() in "TFYN"
        return False

    def _set_char(self, pos, ch):
        self.text = self.text[:pos] + ch + self.text[pos + 1:]

    def _word_left(self):
        pos = self.pos
        while pos > 0 and self.text[pos - 1] == " ":
            pos -= 1
        while pos > 0 and self.text[pos - 1] != " ":
            pos -= 1
        return pos

    def _word_right(self):
        pos = self.pos
        while pos < self.width and self.text[pos] != " ":
            pos += 1
        while pos < self.width and self.text[pos] == " ":
            pos += 1
        return pos

    # ------------------------------------------------------------ teclas
    def key(self, ch, insert=False, word_keys=True):
        """Trata a tecla. Retorna None (tratada), 'full', 'left-edge',
        'right-edge' ou 'unhandled'."""
        if ch == curses.KEY_LEFT:
            if self.pos == self._fix(0, 1):
                return "left-edge"
            self.pos = self._fix(self.pos - 1, -1)
            return None
        if ch == curses.KEY_RIGHT:
            if self.pos >= self.width - 1:
                return "right-edge"
            self.pos = self._fix(self.pos + 1, 1)
            return None
        if word_keys and ch == curses.KEY_HOME:
            if self.pos == self._fix(0, 1):
                return "left-edge"
            self.pos = self._fix(self._word_left(), 1)
            return None
        if word_keys and ch == curses.KEY_END:
            pos = self._word_right()
            if pos >= self.width or not self.text[pos:].strip():
                return "right-edge"
            self.pos = self._fix(pos, 1)
            return None

        if not self.editable:
            if isinstance(ch, str) or is_backspace(ch) or ch in (curses.KEY_DC, 25):
                curses.beep()
                return None
            return "unhandled"

        if ch == 25:  # Ctrl-Y: apaga o campo
            self.text = DATE_BLANK if self.kind == "D" else " " * self.width
            self.home()
            self.dirty = True
            return None

        if ch == curses.KEY_DC or ch == 7:  # Del / Ctrl-G
            self._delete_at(self.pos)
            return None

        if is_backspace(ch):
            if self.pos == self._fix(0, 1):
                curses.beep()
                return None
            self.pos = self._fix(self.pos - 1, -1)
            self._delete_at(self.pos)
            return None

        if isinstance(ch, str):
            if not self._allowed(ch):
                curses.beep()
                return None
            if self.kind == "L":
                ch = ch.upper()
            if self.kind in ("N", "F") and not self.dirty and self.pos == 0:
                self.text = " " * self.width  # 1ª tecla no número limpa o campo
            if insert and self.kind in ("C", "N", "F"):
                self.text = (self.text[:self.pos] + ch + self.text[self.pos:])[:self.width]
            else:
                self._set_char(self.pos, ch)
            self.dirty = True
            if self.pos >= self.width - 1:
                curses.beep()
                return "full"
            self.pos = self._fix(self.pos + 1, 1)
            return None

        return "unhandled"

    def _delete_at(self, pos):
        if self.kind == "D":
            self._set_char(pos, " ")
        else:
            self.text = self.text[:pos] + self.text[pos + 1:] + " "
        self.dirty = True

    # ------------------------------------------------------------- tela
    def draw(self, stdscr, y, x, maxw=None, attr=None, active=False):
        """Desenha o campo; retorna a coluna do cursor."""
        attr = curses.color_pair(ui.C_REVERSE) if attr is None else attr
        maxw = self.width if maxw is None else max(1, min(maxw, self.width))
        if self.pos < self.hscroll:
            self.hscroll = self.pos
        elif self.pos >= self.hscroll + maxw:
            self.hscroll = self.pos - maxw + 1
        if not active:
            self.hscroll = 0
        ui.put(stdscr, y, x, self.text[self.hscroll:self.hscroll + maxw], attr)
        return x + self.pos - self.hscroll
