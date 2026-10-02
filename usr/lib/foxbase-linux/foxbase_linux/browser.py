"""BROWSE, reproduzindo o FoxBASE+ 2.10.

- Caixa de navegação nas linhas 1-6 (F1 liga/desliga); linha 0 livre para o menu.
- Cabeçalho com os nomes completados com '-', colunas separadas por um espaço.
- O registro atual fica em vídeo reverso; o BROWSE começa com ele no topo.
- Mensagem "View and edit fields."; F10 ou ^Home abre o menu:
  Bottom, Top, Record #, fiNd, Skip, Lock, Freeze.
- ↓ no último registro: "Add new records? (Y/N) " -> inclusão ("Add new records.").
- ^U marca/desmarca exclusão, ^Y apaga o campo, ^←/^→ rolam as colunas,
  ^End (ou ^W) grava e sai, Esc sai sem gravar o campo em edição.
"""

import curses

from . import screen, ui
from .dbf import DBFError
from .fieldedit import FieldEditor
from .widgets import (CTRL_END, CTRL_HOME, CTRL_LEFT, CTRL_RIGHT, is_enter, read_key)

MENU_ITEMS = [
    ("Bottom", "Go to the end of the file."),
    ("Top", "Go to the beginning of the file."),
    ("Record #", "Go to a specified record number in the file."),
    ("fiNd", "Locate a record by key in an indexed database."),
    ("Skip", "Skip a number of records forward or backward in the file."),
    ("Lock", "Enter number of fields on the left that are to remain stationary during a pan."),
    ("Freeze", "Enter a single field name to edit."),
]
MENU_POS = [4, 15, 24, 37, 48, 59, 69]


class Browser:
    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.top = 0
        self.left = 0          # primeiro campo rolável visível
        self.field_index = 0
        self.lock = 0          # campos fixos à esquerda (Lock)
        self.freeze = None     # único campo editável (Freeze)
        self.editor = None
        self.editor_key = None
        self.adding = False    # registro novo em inclusão (EOF)
        self.msg = ""
        self.msg_error = False
        self.question = ""

    # -------------------------------------------------------- registro
    @property
    def dbf(self):
        return self.app.current_dbf

    @property
    def row(self):
        return self.app.current_record

    def _editor(self):
        key = (self.row, self.field_index)
        if self.editor is None or self.editor_key != key:
            field = self.dbf.fields[self.field_index]
            raw = self.dbf.records[self.row]["values"][self.field_index]
            self.editor = FieldEditor(self.dbf, field, raw,
                                      blank_zero=not (self.adding and
                                                      self.row == self.dbf.record_count - 1))
            self.editor_key = key
        return self.editor

    def _commit_cell(self):
        editor = self.editor
        if editor is None or not editor.dirty:
            return True
        row, fi = self.editor_key
        try:
            raw = editor.value()
        except DBFError as exc:
            self._error(f"{exc} (press SPACE)")
            return False
        self.dbf.records[row]["values"][fi] = raw
        self.dbf.save()
        editor.dirty = False
        self.editor = None
        return True

    def _error(self, text):
        curses.beep()
        self.msg = text
        self.msg_error = True

    def _record_blank(self, index):
        return all(not v.strip() for v in self.dbf.records[index]["values"])

    def _leave_new_record(self):
        """Saindo de um registro incluído em branco: ele é descartado."""
        if self.adding and self.row == self.dbf.record_count - 1 \
                and self._record_blank(self.row):
            self.dbf.records.pop()
            self.dbf.save()
            self.app.current_record = max(0, self.dbf.record_count - 1)
            self.adding = False
            return True
        return False

    # -------------------------------------------------------- movimento
    def _set_row(self, row):
        if not self._commit_cell():
            return False
        if row != self.row:
            self._leave_new_record()
        row = max(0, min(row, self.dbf.record_count - 1))
        self.app.current_record = row
        self.app.eof = self.app.bof = False
        self.editor = None
        if self.adding and row != self.dbf.record_count - 1:
            self.adding = False
        return True

    def _fields_editable(self):
        if self.freeze is not None:
            return [self.freeze]
        return list(range(len(self.dbf.fields)))

    def _set_field(self, fi, at_end=False):
        if not self._commit_cell():
            return False
        self.field_index = fi
        self.editor = None
        if at_end:
            self._editor().end()
        return True

    def _next_field(self):
        fields = self._fields_editable()
        pos = fields.index(self.field_index) if self.field_index in fields else -1
        if pos + 1 < len(fields):
            self._set_field(fields[pos + 1])
        else:
            if self.row < self.dbf.record_count - 1:
                if self._set_row(self.row + 1):
                    self.field_index = fields[0]
            else:
                self._down()
                self.field_index = fields[0]

    def _prev_field(self, at_end=False):
        fields = self._fields_editable()
        pos = fields.index(self.field_index) if self.field_index in fields else 0
        if pos > 0:
            self._set_field(fields[pos - 1], at_end)
        elif self.row > 0 and self._set_row(self.row - 1):
            self._set_field(fields[-1], at_end)

    def _down(self):
        if self.row < self.dbf.record_count - 1:
            self._set_row(self.row + 1)
            return
        if not self._commit_cell():
            return
        if self.adding:
            if self._record_blank(self.row):
                curses.beep()
                return
            self._add_record()
            return
        self.question = "Add new records? (Y/N) "
        self._draw()
        answer = screen.ask_yn(self.app.stdscr, read_key, self.question)
        self.question = ""
        if answer:
            self._add_record()

    def _add_record(self):
        self.dbf.append_blank()
        self.adding = True
        self._set_row(self.dbf.record_count - 1)
        self.adding = True
        fields = self._fields_editable()
        self.field_index = fields[0]

    # ------------------------------------------------------------- tela
    def _col_width(self, fi):
        field = self.dbf.fields[fi]
        return max(len(field["name"]), self.dbf.display_width(field))

    def _columns(self, w):
        """Colunas visíveis: (field_index, x, largura da coluna)."""
        n = len(self.dbf.fields)
        lock = min(self.lock, n)
        self.left = max(self.left, lock)
        if self.field_index >= lock and self.field_index < self.left:
            self.left = self.field_index
        while True:
            columns = []
            x = 0
            order = list(range(lock)) + list(range(self.left, n))
            for fi in order:
                width = min(self._col_width(fi), w - 1)
                if columns and x + width > w:
                    break
                columns.append((fi, x, width))
                x += width + 1
            visible = [c[0] for c in columns]
            if self.field_index in visible or self.left >= n - 1:
                return columns
            self.left += 1

    def _draw(self):
        stdscr = self.app.stdscr
        dbf = self.dbf
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        y = 1
        if self.app.show_help:
            y = screen.help_box(stdscr, screen.HELP_BROWSE, y=1)
        header_y = y
        columns = self._columns(w)
        for fi, x, width in columns:
            ui.put(stdscr, header_y, x, dbf.fields[fi]["name"].ljust(width, "-")[:width])

        first = header_y + 1
        visible = max(1, h - 3 - first)
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + visible:
            self.top = self.row - visible + 1

        cursor = None
        rev = curses.color_pair(ui.C_REVERSE)
        for screen_row in range(visible):
            index = self.top + screen_row
            if index >= dbf.record_count:
                break
            yy = first + screen_row
            record = dbf.records[index]
            current = index == self.row
            for fi, x, width in columns:
                field = dbf.fields[fi]
                fw = min(dbf.display_width(field), width)
                if current and fi == self.field_index:
                    cx = self._editor().draw(stdscr, yy, x, fw, rev, active=True)
                    cursor = (yy, cx)
                else:
                    value = dbf.display_value(field, record["values"][fi])
                    if self.adding and current and field["type"] in ("N", "F") \
                            and not record["values"][fi].strip() and not field["decimals"]:
                        value = " " * field["length"]
                    ui.put(stdscr, yy, x, value[:fw].ljust(fw), rev if current else 0)

        if dbf.record_count and not self.adding:
            deleted = dbf.records[self.row]["deleted"]
            info = f"Rec: {self.row + 1}/{dbf.record_count}"
        elif self.adding:
            deleted = False
            info = f"Rec: EOF/{dbf.record_count - 1}"
        else:
            deleted = False
            info = "Rec: None"
        screen.status_bar(stdscr, "BROWSE", dbf.filename, info,
                          screen.flags_text(self.app.insert_mode, deleted))
        screen.message(stdscr, self.question or self.msg, 2, error=self.msg_error)
        screen.message(stdscr, "Add new records." if self.adding else "View and edit fields.", 1)
        if cursor:
            curses.curs_set(1)
            try:
                stdscr.move(*cursor)
            except curses.error:
                pass
        else:
            curses.curs_set(0)
        stdscr.refresh()

    # ------------------------------------------------------------- menu
    def _menu(self):
        if not self._commit_cell():
            return
        stdscr = self.app.stdscr
        bar = screen.OptionBar(MENU_ITEMS, MENU_POS)
        while True:
            self._draw()
            bar.draw(stdscr)
            curses.curs_set(0)
            stdscr.refresh()
            choice = bar.key(read_key(stdscr))
            if choice is None:
                continue
            if choice == -1:
                return
            self._menu_action(choice)
            return

    def _ask(self, index, label, default=""):
        stdscr = self.app.stdscr
        self._draw()
        bar = screen.OptionBar(MENU_ITEMS, MENU_POS)
        bar.index = index
        bar.draw(stdscr)
        screen.message(stdscr, "Enter new value.  Finish with ◄┘", 2)
        x = max(0, MENU_POS[index] - 1)
        return screen.popup_input(stdscr, read_key, x, label, default)

    def _menu_action(self, choice):
        dbf = self.dbf
        n = dbf.record_count
        if choice == 0:  # Bottom
            if self._set_row(n - 1):
                self.top = self.row
        elif choice == 1:  # Top
            if self._set_row(0):
                self.top = self.row
        elif choice == 2:  # Record #
            value = self._ask(2, "Enter new record #: ")
            if value is None:
                return
            if not value.strip().isdigit() or not 1 <= int(value) <= n:
                self._error(f"Range is 1 to {n} (press SPACE)")
                return
            if self._set_row(int(value) - 1):
                self.top = self.row
        elif choice == 3:  # fiNd
            self._ask(3, "Enter key to find: ")
            self._error("Database is not indexed.")
        elif choice == 4:  # Skip
            value = self._ask(4, "Enter number to skip: ")
            if value is None:
                return
            try:
                count = int(value.strip())
            except ValueError:
                self._error("Illegal value (press SPACE)")
                return
            if self._set_row(self.row + count):
                self.top = self.row
        elif choice == 5:  # Lock
            value = self._ask(5, "Enter number of fields: ")
            if value is None:
                return
            fields = len(dbf.fields)
            if not value.strip().isdigit() or int(value) > fields:
                self._error(f"Range is 0 to {fields} (press SPACE)")
                return
            self.lock = int(value)
            self.left = self.lock
        elif choice == 6:  # Freeze
            value = self._ask(6, "Enter field name: ",
                              dbf.fields[self.freeze]["name"] if self.freeze is not None else "")
            if value is None:
                return
            if not value.strip():
                self.freeze = None
                return
            fi = dbf.field_index(value)
            if fi < 0:
                self._error("No such field (press SPACE)")
                return
            self.freeze = fi
            self._set_field(fi)

    # ------------------------------------------------------------- loop
    def run(self):
        dbf = self.dbf
        self.editor = None
        self.adding = False
        self.msg, self.msg_error = "", False
        if not dbf.record_count:
            self._draw()
            if not screen.ask_yn(self.app.stdscr, read_key, "Add new records? (Y/N) "):
                return
            self._add_record()
        if self.app.eof or self.app.current_record >= dbf.record_count:
            self.app.current_record = dbf.record_count - 1
            self.app.eof = False
        self.top = self.app.current_record
        if self.freeze is not None and self.freeze >= len(dbf.fields):
            self.freeze = None
        self.field_index = self.freeze if self.freeze is not None else \
            min(self.field_index, len(dbf.fields) - 1)

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
            page = max(1, h - 4 - (len(screen.HELP_BROWSE) if self.app.show_help else 0))

            if ch == curses.KEY_F1:
                self.app.show_help = not self.app.show_help
            elif ch in (curses.KEY_F10, CTRL_HOME):
                self._menu()
            elif ch == curses.KEY_IC:
                self.app.insert_mode = not self.app.insert_mode
            elif ch == 27:
                self.editor = None
                self._leave_new_record()
                break
            elif ch in (CTRL_END, 23):  # ^End / ^W
                if self._commit_cell():
                    self._leave_new_record()
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
                if self.row >= dbf.record_count - 1:
                    self._down()
                else:
                    self._set_row(self.row + page)
            elif ch == CTRL_LEFT:
                if self._commit_cell() and self.left > self.lock:
                    self.left -= 1
                    if self.field_index >= self.lock and self.field_index > self.left \
                            and self.freeze is None:
                        self.field_index -= 1
            elif ch == CTRL_RIGHT:
                width = self.app.stdscr.getmaxyx()[1]
                last_visible = self._columns(width)[-1][0]
                if self._commit_cell() and last_visible < len(dbf.fields) - 1:
                    self.left += 1
                    if self.field_index >= self.lock and self.field_index < self.left \
                            and self.freeze is None:
                        self.field_index = self.left
            elif ch == 21:  # ^U
                if not self.adding:
                    record = dbf.records[self.row]
                    if record["deleted"]:
                        dbf.recall(self.row)
                    else:
                        dbf.delete(self.row)
            elif ch == 9 or is_enter(ch):
                self._next_field()
            elif ch == curses.KEY_BTAB:
                self._prev_field()
            else:
                result = self._editor().key(ch, self.app.insert_mode)
                if result in ("full", "right-edge"):
                    self._next_field()
                elif result == "left-edge":
                    self._prev_field(at_end=True)

        self.app.eof = False
