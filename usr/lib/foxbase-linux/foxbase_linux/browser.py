"""BROWSE em tela cheia, no estilo dBASE III PLUS / FoxBASE+.

- Grade com os nomes dos campos no topo e colunas separadas por │.
- Edição direto na célula: digitar sobrescreve (Ins alterna), campo cheio -> próximo.
- ↑↓ registro, Enter/Tab/End próximo campo, Home campo anterior, ^← ^→ rola colunas.
- PgUp/PgDn página; ↓ no último registro pergunta "Add new records? (Y/N)".
- ^U marca/desmarca exclusão ("Del" na barra de status); ^Y apaga o campo.
- ^End (ou ^W) grava e sai; Esc sai sem gravar o registro atual; F1 ajuda.
"""

import curses

from . import screen, ui
from .dbf import DBFError
from .fieldedit import FieldEditor
from .widgets import CTRL_END, CTRL_LEFT, CTRL_RIGHT, is_enter, read_key


class Browser:
    def __init__(self, app):
        self.app = app
        self.top = 0
        self.left = 0  # primeiro campo visível
        self.field_index = 0
        self.editor = None
        self.editor_row = None
        self.msg = ""
        self.msg_error = False

    def reset(self):
        self.top = 0
        self.left = 0
        self.field_index = 0

    # -------------------------------------------------------- registro
    @property
    def dbf(self):
        return self.app.current_dbf

    @property
    def row(self):
        return self.app.current_record

    def _editor(self):
        """Editor da célula atual (recriado quando muda de célula)."""
        key = (self.row, self.field_index)
        if self.editor is None or self.editor_row != key:
            field = self.dbf.fields[self.field_index]
            raw = self.dbf.records[self.row]["values"][self.field_index]
            self.editor = FieldEditor(self.dbf, field, raw)
            self.editor_row = key
        return self.editor

    def _commit_cell(self):
        """Grava a célula atual se mudou. Retorna False se o valor é inválido."""
        editor = self.editor
        if editor is None or not editor.dirty:
            return True
        row, fi = self.editor_row
        try:
            raw = editor.value()
        except DBFError as exc:
            self._error(f"{exc}  (press SPACE)" if editor.kind == "D" else str(exc))
            return False
        self.dbf.records[row]["values"][fi] = raw
        self.dbf.save()
        editor.dirty = False
        self.editor = None
        return True

    def _discard_cell(self):
        self.editor = None

    def _error(self, text):
        curses.beep()
        self.msg = text
        self.msg_error = True

    # -------------------------------------------------------- movimento
    def _set_row(self, row):
        if not self._commit_cell():
            return False
        self.app.current_record = max(0, min(row, self.dbf.record_count - 1))
        self.app.eof = False
        self.editor = None
        return True

    def _set_field(self, fi, at_end=False):
        if not self._commit_cell():
            return False
        self.field_index = max(0, min(fi, len(self.dbf.fields) - 1))
        self.editor = None
        if at_end:
            self._editor().end()
        return True

    def _next_field(self):
        if self.field_index < len(self.dbf.fields) - 1:
            self._set_field(self.field_index + 1)
        elif self.row < self.dbf.record_count - 1:
            if self._set_row(self.row + 1):
                self.field_index = 0
                self.left = 0
        else:
            self._down()

    def _prev_field(self, at_end=False):
        if self.field_index > 0:
            self._set_field(self.field_index - 1, at_end)
        elif self.row > 0:
            if self._set_row(self.row - 1):
                self._set_field(len(self.dbf.fields) - 1, at_end)

    def _down(self):
        if self.row < self.dbf.record_count - 1:
            self._set_row(self.row + 1)
            return
        if not self._commit_cell():
            return
        self._draw()
        if screen.ask_yn(self.app.stdscr, read_key, "Add new records? (Y/N)"):
            self.dbf.append_blank()
            self._set_row(self.dbf.record_count - 1)
            self.field_index = 0
            self.left = 0

    # ------------------------------------------------------------- tela
    def _columns(self, w):
        """Colunas visíveis: (field_index, x, largura)."""
        if self.field_index < self.left:
            self.left = self.field_index
        while True:
            columns = []
            x = 0
            for fi in range(self.left, len(self.dbf.fields)):
                field = self.dbf.fields[fi]
                width = max(self.dbf.display_width(field), len(field["name"]))
                width = min(width, w - 2)
                if columns and x + width > w - 1:
                    break
                columns.append((fi, x, width))
                x += width + 1
            if any(c[0] == self.field_index for c in columns) or self.left >= self.field_index:
                return columns
            self.left += 1

    def _draw(self):
        stdscr = self.app.stdscr
        dbf = self.dbf
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        y = 0
        if self.app.show_help:
            y = screen.help_box(stdscr, screen.HELP_BROWSE)

        columns = self._columns(w)
        header_y = y
        for fi, x, width in columns:
            ui.put(stdscr, header_y, x, dbf.fields[fi]["name"][:width].ljust(width), curses.A_BOLD)
            if x + width < w - 1:
                ui.put(stdscr, header_y, x + width, "│")

        first = header_y + 1
        visible = max(1, h - 2 - first)
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + visible:
            self.top = self.row - visible + 1

        cursor = None
        rev = curses.color_pair(ui.C_REVERSE)
        for screen_row in range(visible):
            index = self.top + screen_row
            yy = first + screen_row
            if index >= dbf.record_count:
                break
            record = dbf.records[index]
            for fi, x, width in columns:
                field = dbf.fields[fi]
                if index == self.row and fi == self.field_index:
                    editor = self._editor()
                    cx = editor.draw(stdscr, yy, x, width, rev, active=True)
                    cursor = (yy, cx)
                else:
                    value = dbf.display_value(field, record["values"][fi])
                    if field["type"] in ("N", "F"):
                        value = value.rjust(dbf.display_width(field))
                    ui.put(stdscr, yy, x, value[:width].ljust(width),
                           rev if index == self.row else 0)
                if x + width < w - 1:
                    ui.put(stdscr, yy, x + width, "│")

        if dbf.record_count:
            deleted = dbf.records[self.row]["deleted"]
            info = f"Rec: {self.row + 1}/{dbf.record_count}"
        else:
            deleted = False
            info = "Rec: None"
        screen.status_bar(stdscr, "BROWSE", dbf.filename, info,
                          screen.flags_text(self.app.insert_mode, deleted))
        screen.message(stdscr, self.msg, error=self.msg_error)
        if cursor:
            curses.curs_set(1)
            try:
                stdscr.move(*cursor)
            except curses.error:
                pass
        else:
            curses.curs_set(0)
        stdscr.refresh()

    # ------------------------------------------------------------- loop
    def run(self):
        dbf = self.dbf
        if not dbf:
            return
        self.editor = None
        if not dbf.record_count:
            self._draw()
            if not screen.ask_yn(self.app.stdscr, read_key, "Add new records? (Y/N)"):
                return
            dbf.append_blank()
            self.app.current_record = 0
        if self.app.current_record >= dbf.record_count:
            self.app.current_record = dbf.record_count - 1
        self.field_index = min(self.field_index, len(dbf.fields) - 1)

        while True:
            self._draw()
            ch = read_key(self.app.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            if self.msg_error:
                self.msg, self.msg_error = "", False
                if ch == " ":
                    continue
            else:
                self.msg = ""

            h = self.app.stdscr.getmaxyx()[0]
            page = max(1, h - 4 - (screen.HELP_HEIGHT if self.app.show_help else 0))

            if ch == curses.KEY_F1:
                self.app.show_help = not self.app.show_help
            elif ch == curses.KEY_IC:
                self.app.insert_mode = not self.app.insert_mode
            elif ch == 27:
                self._discard_cell()
                break
            elif ch in (CTRL_END, 23):  # ^End / ^W
                if self._commit_cell():
                    break
            elif ch == curses.KEY_UP:
                if self.row > 0:
                    self._set_row(self.row - 1)
                else:
                    curses.beep()
            elif ch == curses.KEY_DOWN:
                self._down()
            elif ch == curses.KEY_PPAGE:
                self._set_row(self.row - page)
            elif ch == curses.KEY_NPAGE:
                self._set_row(self.row + page)
            elif ch == CTRL_LEFT:
                if self._commit_cell() and self.left > 0:
                    self.left -= 1
                    self.field_index = max(self.field_index - 1, self.left) \
                        if self.field_index > self.left else self.left
            elif ch == CTRL_RIGHT:
                if self._commit_cell() and self.left < len(dbf.fields) - 1:
                    self.left += 1
                    self.field_index = max(self.field_index, self.left)
            elif ch == 21:  # ^U
                record = dbf.records[self.row]
                if record["deleted"]:
                    dbf.recall(self.row)
                else:
                    dbf.delete(self.row)
            elif ch == 9 or is_enter(ch) or ch == curses.KEY_END:
                self._next_field()
            elif ch in (curses.KEY_BTAB, curses.KEY_HOME):
                self._prev_field()
            else:
                result = self._editor().key(ch, self.app.insert_mode, word_keys=False)
                if result in ("full", "right-edge"):
                    self._next_field()
                elif result == "left-edge":
                    self._prev_field(at_end=True)

        self.app.eof = False
