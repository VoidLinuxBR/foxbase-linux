"""EDIT / CHANGE / APPEND em tela cheia, no estilo dBASE III PLUS / FoxBASE+.

- Todos os campos do registro na tela: nome à esquerda, valor em vídeo reverso.
- Digitar sobrescreve (Ins alterna inserção); campo cheio -> próximo campo, com bipe.
- Enter/↓ próximo campo, ↑ anterior; PgDn/PgUp próximo/anterior registro.
- ^End (ou ^W) grava e sai; Esc sai sem gravar o registro atual.
- ^U marca/desmarca exclusão; ^Y apaga o campo; F1 mostra/esconde a ajuda.
- APPEND: Enter no primeiro campo de um registro em branco encerra o APPEND;
  registro em branco não é gravado.
"""

import curses

from . import screen, ui
from .dbf import DBFError
from .fieldedit import FieldEditor
from .widgets import CTRL_END, CTRL_HOME, is_enter, read_key

NAME_COL = 0
VALUE_COL = 11


class RecordForm:
    def __init__(self, app, mode, index=None):
        self.app = app
        self.stdscr = app.stdscr
        self.dbf = app.current_dbf
        self.mode = mode  # "EDIT", "CHANGE" ou "APPEND"
        self.append = mode == "APPEND"
        self.index = index  # None = registro novo (APPEND)
        self.field_index = 0
        self.top = 0
        self.msg = ""
        self.msg_error = False
        self.deleted = False
        self.deleted_changed = False
        self.editors = []
        self._load(index)

    # ---------------------------------------------------------- registro
    def _load(self, index):
        self.index = index
        if index is None:
            values = self.dbf.blank_values()
            self.deleted = False
        else:
            record = self.dbf.records[index]
            values = record["values"]
            self.deleted = record["deleted"]
            self.app.current_record, self.app.eof = index, False
        self.deleted_changed = False
        self.editors = [FieldEditor(self.dbf, f, v) for f, v in zip(self.dbf.fields, values)]
        self.memo_values = {}
        self.field_index = 0
        self.top = 0

    def _dirty(self):
        return self.deleted_changed or any(e.dirty for e in self.editors)

    def _blank(self):
        return all(e.is_blank() for e in self.editors if e.editable)

    def _commit(self):
        """Grava o registro atual. Retorna True se ok (ou nada a gravar)."""
        if not self._dirty():
            return True
        values = []
        for fi, editor in enumerate(self.editors):
            if not editor.editable:
                if fi in self.memo_values:
                    values.append(self.memo_values[fi])
                else:
                    values.append(self.dbf.records[self.index]["values"][fi]
                                  if self.index is not None else "")
                continue
            try:
                values.append(editor.value())
            except DBFError as exc:
                self.field_index = fi
                self._error(str(exc))
                return False
        if self.index is None:
            if self._blank():
                return True  # registro em branco não é gravado
            self.dbf.records.append({"deleted": False, "values": values})
            self.index = len(self.dbf.records) - 1
        else:
            self.dbf.records[self.index]["values"] = values
            self.dbf.records[self.index]["deleted"] = self.deleted
        self.dbf.save()
        for editor in self.editors:
            editor.dirty = False
        self.deleted_changed = False
        self.app.current_record = self.index
        self.app.eof = False
        return True

    def _edit_memo(self, editor):
        from .editor import edit_memo
        fi = self.field_index
        raw = self.dbf.records[self.index]["values"][fi] if self.index is not None else ""
        text = edit_memo(self.app, self.dbf.read_memo(raw), editor.field["name"])
        if text is None:
            return
        if self.index is None:
            if not self._commit_blank_ok():
                return
        new_raw = self.dbf.write_memo(text)
        self.memo_values[fi] = new_raw
        editor.text = self.dbf.display_value(editor.field, new_raw)
        editor.dirty = True

    def _commit_blank_ok(self):
        return True

    def _error(self, text):
        curses.beep()
        self.msg = text
        self.msg_error = True

    # -------------------------------------------------------- navegação
    def _leave_field(self):
        """Valida/normaliza o campo atual antes de sair dele."""
        editor = self.editors[self.field_index]
        try:
            editor.normalize()
        except DBFError as exc:
            self._error(f"{exc} (press SPACE)")
            return False
        return True

    def _go_field(self, new_index, at_end=False):
        if not self._leave_field():
            return
        self.field_index = new_index
        editor = self.editors[new_index]
        if at_end:
            editor.end()
        else:
            editor.home()

    def _next_field(self):
        """Retorna 'next-record' quando passa do último campo."""
        if self.field_index >= len(self.editors) - 1:
            if not self._leave_field():
                return None
            return "next-record"
        self._go_field(self.field_index + 1)
        return None

    def _prev_field(self, at_end=False):
        if self.field_index == 0:
            if not self._leave_field():
                return None
            return "prev-record"
        self._go_field(self.field_index - 1, at_end)
        return None

    def _next_record(self):
        """PgDn: retorna True se deve sair."""
        if not self._leave_field() or not self._commit():
            return False
        if self.append:
            if self.index is None:
                if self._blank():
                    return True  # Enter/PgDn em registro em branco termina
                return False
            if self.index < self.dbf.record_count - 1:
                self._load(self.index + 1)
            else:
                self._load(None)
            return False
        if self.index >= self.dbf.record_count - 1:
            self.app.eof = True  # EDIT: passar do último registro sai em EOF
            self.exit_eof = True
            return True
        self._load(self.index + 1)
        return False

    def _prev_record(self):
        if not self._leave_field() or not self._commit():
            return
        if self.index is None:
            target = self.dbf.record_count - 1
        else:
            target = self.index - 1
        if target < 0:
            self.exit_top = True  # PgUp no primeiro registro sai do EDIT
            return
        self._load(target)

    # -------------------------------------------------------------- tela
    def _draw(self):
        stdscr = self.stdscr
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        top_row = 1
        if self.app.show_help:
            top_row = screen.help_box(stdscr, screen.HELP_EDIT, y=1)
        rows = max(1, h - 3 - top_row)

        if self.field_index < self.top:
            self.top = self.field_index
        elif self.field_index >= self.top + rows:
            self.top = self.field_index - rows + 1

        cursor = None
        maxw = w - VALUE_COL - 1
        for row in range(rows):
            fi = self.top + row
            if fi >= len(self.editors):
                break
            editor = self.editors[fi]
            y = top_row + row
            ui.put(stdscr, y, NAME_COL, editor.field["name"])
            active = fi == self.field_index
            cx = editor.draw(stdscr, y, VALUE_COL, maxw, active=active)
            if active:
                cursor = (y, cx)

        count = self.dbf.record_count
        if self.index is None:
            info = f"Rec: EOF/{count}"
        else:
            info = f"Rec: {self.index + 1}/{count}"
        screen.status_bar(stdscr, self.mode, self.dbf.filename, info,
                          screen.flags_text(self.app.insert_mode, self.deleted))
        screen.message(stdscr, "", 2)
        screen.message(stdscr, self.msg or "Enter a FoxBASE+ command", 1,
                       error=self.msg_error)
        if cursor:
            curses.curs_set(1)
            try:
                stdscr.move(*cursor)
            except curses.error:
                pass
        stdscr.refresh()

    # -------------------------------------------------------------- loop
    def run(self):
        if not self.dbf.fields:
            return
        while True:
            self._draw()
            ch = read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            if self.msg_error:
                self.msg, self.msg_error = "", False
                if ch == " ":
                    continue
            else:
                self.msg = ""

            editor = self.editors[self.field_index]

            if ch == curses.KEY_F1:
                self.app.show_help = not self.app.show_help
            elif ch == curses.KEY_IC:
                self.app.insert_mode = not self.app.insert_mode
            elif ch == 27:
                return  # abandona o registro atual
            elif ch in (CTRL_END, 23):  # ^End / ^W
                if self._leave_field() and self._commit():
                    return
            elif ch == CTRL_HOME:  # ^Home: editar memo
                if editor.kind == "M":
                    self._edit_memo(editor)
                else:
                    curses.beep()
            elif ch == 21:  # ^U
                if self.index is None:
                    curses.beep()
                else:
                    self.deleted = not self.deleted
                    self.deleted_changed = True
            elif ch == curses.KEY_NPAGE:
                if self._next_record():
                    return
            elif ch == curses.KEY_PPAGE:
                self._prev_record()
                if getattr(self, "exit_top", False):
                    return
            elif is_enter(ch):
                if (self.append and self.index is None and self.field_index == 0
                        and self._blank() and not self._dirty()):
                    return  # Enter num registro novo em branco termina o APPEND
                if self._next_field() == "next-record" and self._next_record():
                    return
            elif ch in (curses.KEY_DOWN, 9):
                if self._next_field() == "next-record" and self._next_record():
                    return
            elif ch in (curses.KEY_UP, curses.KEY_BTAB):
                if self._prev_field() == "prev-record":
                    self._prev_record()
            else:
                result = editor.key(ch, self.app.insert_mode)
                if result == "full" or result == "right-edge":
                    if self._next_field() == "next-record" and self._next_record():
                        return
                elif result == "left-edge":
                    if self._prev_field(at_end=True) == "prev-record":
                        self._prev_record()


def edit_record(app, index, mode="EDIT"):
    RecordForm(app, mode, index).run()


def append_records(app):
    form = RecordForm(app, "APPEND", None)
    form.run()
    if form.index is None:  # saiu num registro novo em branco: ponteiro em EOF
        app.current_record = max(0, app.current_dbf.record_count - 1)
        app.eof = True
