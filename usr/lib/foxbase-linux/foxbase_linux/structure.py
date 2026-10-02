"""CREATE / MODIFY STRUCTURE, reproduzindo o FoxBASE+ 2.10.

Layout: "Bytes remaining" na linha 1, caixa de navegação (F1) nas linhas 3-8,
"field name  type     width  dec" em duas colunas com a linha ═ embaixo e os
campos numerados. Mensagens nas duas últimas linhas, como no original.
^Home abre o menu (Bottom, Top, Field #, Save, Abandon); ^End grava
("Press ENTER to confirm.  Any other key to resume."); Esc abandona.
"""

import copy
import curses
import shutil
from pathlib import Path

from . import screen, settings, ui
from .dbf import DBF, DBFError
from .widgets import (CTRL_END, CTRL_HOME, LineEdit, is_backspace, is_enter, read_key)

MAX_RECORD = 4000
MAX_FIELDS = 128
TYPES = ["C", "N", "D", "L", "M"]
TYPE_NAMES = {"C": "Character", "N": "Numeric", "D": "Date", "L": "Logical", "M": "Memo"}
FIXED_WIDTH = {"D": 8, "L": 1, "M": 10}

MSG_FIELD = {
    "name": "Enter the name field.",
    "type": "Press SPACE to change the field type",
    "width": "Enter the field width.",
    "dec": "Enter the number of decimal places.",
}
MSG_NAME = "Field names begin with a letter and may contain letters, digits and underscores"
MSG_TYPE = {
    "C": "CHARACTER fields contain character information of a specified length.",
    "N": "NUMERIC fields contain signed numbers that may be either integer or decimal.",
    "D": "DATE fields have the form mm/dd/yy unless otherwise specified.",
    "L": "LOGICAL fields have a value of either T or F.",
    "M": "MEMO fields contains character information of varying lengths.",
}
MSG_WIDTH = {
    "C": "Character fields are 1 to 254 positions wide.",
    "N": "Numeric fields are 1 to 19 digits wide, including the decimal point and sign.",
}
MSG_DEC = "Decimal widths are 1 to 15 and must be at least 2 less than the field width."

MENU_ITEMS = [
    ("Bottom", "Go to the last field in the file structure."),
    ("Top", "Go to the first field in the file structure."),
    ("Field #", "Go to a specified field name."),
    ("Save", "Toggle cursor menu."),
    ("Abandon", "Toggle cursor menu."),
]
MENU_POS = [1, 12, 20, 32, 41]

HEADER = "field name  type     width  dec"
RULE = "═" * 31
CELL_X = {"name": 5, "type": 17, "width": 28, "dec": 33}
CELL_W = {"name": 10, "type": 9, "width": 3, "dec": 3}
COLUMN_OFFSET = 44


def _blank_row():
    return {"name": "", "type": "C", "width": 0, "dec": 0, "orig": None}


class StructureEditor:
    def __init__(self, app, path, existing=None):
        self.app = app
        self.stdscr = app.stdscr
        self.path = Path(path)
        self.modify = existing is not None
        self.existing = existing
        self.rows = []
        if existing:
            for index, field in enumerate(existing.fields):
                kind = field["type"] if field["type"] in TYPES else "C"
                self.rows.append({
                    "name": field["name"], "type": kind,
                    "width": field["length"],
                    "dec": field["decimals"] if kind == "N" else 0,
                    "orig": index,
                })
        if not self.rows:
            self.rows.append(_blank_row())
        self.row = 0
        self.col = "name"
        self.edit = None
        self.page_top = 0
        self._start_cell()

    # ------------------------------------------------------------ regras
    def _bytes_remaining(self):
        return MAX_RECORD - sum(int(r["width"]) for r in self.rows if r["name"])

    def _cell_text(self, row, col):
        if col == "name":
            return row["name"]
        if col == "type":
            return TYPE_NAMES[row["type"]]
        return str(row[col])

    def _start_cell(self):
        row = self.rows[self.row]
        if self.col in ("name", "width", "dec"):
            text = row["name"] if self.col == "name" else ""
            self.edit = LineEdit(text, CELL_W[self.col])
            self.edit.pos = 0
            self.edit.dirty = False
        else:
            self.edit = None

    def _commit_cell(self):
        """Valida e grava a célula atual; retorna mensagem de erro ou None."""
        row = self.rows[self.row]
        if self.col == "name":
            name = self.edit.text.strip().upper()
            if not name:
                row["name"] = ""
                return None
            if not name[0].isalpha() or not all(c.isalnum() or c == "_" for c in name) \
                    or not name.isascii():
                return "Illegal field name"
            for i, other in enumerate(self.rows):
                if i != self.row and other["name"] == name:
                    return "Field name is already in use."
            row["name"] = name
        elif self.col in ("width", "dec"):
            if not self.edit.dirty:
                return None
            text = self.edit.text.strip()
            value = int(text) if text.isdigit() else 0
            if self.col == "width":
                limit = 254 if row["type"] == "C" else 19
                if not 1 <= value <= limit:
                    return "Illegal data length"
                if self._bytes_remaining() + int(row["width"]) - value < 0:
                    return "Maximum record length exceeded."
                row["width"] = value
            else:
                if value and (value > 15 or value > int(row["width"]) - 2):
                    return "Illegal decimal length"
                row["dec"] = value
        elif self.col == "type":
            fixed = FIXED_WIDTH.get(row["type"])
            if fixed:
                row["width"], row["dec"] = fixed, 0
            elif row["type"] == "C":
                row["dec"] = 0
        return None

    def _cols(self, row):
        if row["type"] == "N":
            return ["name", "type", "width", "dec"]
        if row["type"] == "C":
            return ["name", "type", "width"]
        return ["name", "type"]

    # -------------------------------------------------------- movimento
    def _leave(self):
        error = self._commit_cell()
        if error:
            screen.error_wait(self.stdscr, read_key, error)
            self._start_cell()
            return False
        return True

    def _goto(self, row, col="name"):
        if not self._leave():
            return False
        current = self.rows[self.row]
        if row != self.row:
            if current["name"] and current["type"] in ("C", "N") and not current["width"]:
                screen.error_wait(self.stdscr, read_key, "Illegal data length")
                self.col = "width"
                self._start_cell()
                return False
            if not current["name"] and self.row == len(self.rows) - 1 and len(self.rows) > 1 \
                    and row < self.row:
                self.rows.pop()
        if row >= len(self.rows):
            if not self.rows[-1]["name"]:
                row = len(self.rows) - 1
            elif len(self.rows) >= MAX_FIELDS:
                screen.error_wait(self.stdscr, read_key, "Maximum number of fields exceeded.")
                return False
            else:
                self.rows.append(_blank_row())
        self.row = max(0, min(row, len(self.rows) - 1))
        self.col = col if col in self._cols(self.rows[self.row]) else "name"
        self._start_cell()
        return True

    def _next(self):
        """Enter: próxima célula. Retorna 'save' para nome em branco no fim."""
        row = self.rows[self.row]
        if self.col == "name" and not self.edit.text.strip():
            if self.row == len(self.rows) - 1:
                return "save"
            screen.error_wait(self.stdscr, read_key, "Illegal field name")
            return None
        if not self._leave():
            return None
        cols = self._cols(row)
        index = cols.index(self.col)
        if index + 1 < len(cols):
            self.col = cols[index + 1]
            self._start_cell()
        else:
            self._goto(self.row + 1)
        return None

    def _prev(self):
        if not self._leave():
            return
        cols = self._cols(self.rows[self.row])
        index = cols.index(self.col)
        if index > 0:
            self.col = cols[index - 1]
            self._start_cell()
        elif self.row > 0:
            if self._goto(self.row - 1):
                self.col = self._cols(self.rows[self.row])[-1]
                self._start_cell()

    # ------------------------------------------------------------ tela
    def _draw(self, line0=None):
        stdscr = self.stdscr
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        if line0:
            ui.put(stdscr, 0, 0, line0)
        ui.put(stdscr, 1, 55, f"Bytes remaining:{self._bytes_remaining():7d}")
        y = 2
        if self.app.show_help:
            screen.help_box(stdscr, screen.HELP_CREATE, y=3)
            y = 10
        for off in (0, COLUMN_OFFSET):
            ui.put(stdscr, y, 5 + off, HEADER)
            ui.put(stdscr, y + 1, 5 + off, RULE, curses.color_pair(ui.C_BORDER))
        first = y + 2
        per_col = max(1, h - 3 - first)
        per_page = per_col * 2
        if self.row < self.page_top or self.row >= self.page_top + per_page:
            self.page_top = (self.row // per_page) * per_page

        cursor = None
        rev = curses.color_pair(ui.C_REVERSE)
        for slot in range(per_page):
            index = self.page_top + slot
            if index >= len(self.rows):
                break
            row = self.rows[index]
            off = COLUMN_OFFSET if slot >= per_col else 0
            yy = first + slot % per_col
            ui.put(stdscr, yy, off, f"{index + 1:3d}")
            current = index == self.row
            for col in ("name", "type", "width", "dec"):
                x = CELL_X[col] + off
                width = CELL_W[col]
                if current and col == self.col and self.edit is not None:
                    text = self.edit.text.ljust(width)
                    if col != "name" and not self.edit.dirty:
                        text = str(row[col]).rjust(width)
                    ui.put(stdscr, yy, x, text[:width], rev)
                    cursor = (yy, x + min(self.edit.pos, width - 1))
                    continue
                text = self._cell_text(row, col)
                text = text.rjust(width) if col in ("width", "dec") else text.ljust(width)
                ui.put(stdscr, yy, x, text, rev if current else 0)
                if current and col == self.col:
                    cursor = (yy, x)

        mode = "MODIFY STRUCTURE" if self.modify else "CREATE"
        screen.status_bar(stdscr, mode, self.path if self.modify else "",
                          f"Field: {self.row + 1}/{len(self.rows)}",
                          "Ins" if self.app.insert_mode else "")
        row = self.rows[self.row]
        if self.col == "name":
            help_text = MSG_NAME
        elif self.col == "type":
            help_text = MSG_TYPE[row["type"]]
        elif self.col == "width":
            help_text = MSG_WIDTH.get(row["type"], "")
        else:
            help_text = MSG_DEC
        screen.messages(stdscr, MSG_FIELD[self.col], help_text)
        if cursor and not line0:
            curses.curs_set(1)
            try:
                stdscr.move(*cursor)
            except curses.error:
                pass
        stdscr.refresh()

    # ----------------------------------------------------------- menu
    def _menu(self):
        if not self._leave():
            return None
        bar = screen.OptionBar(MENU_ITEMS, MENU_POS, screen.MSG_SELECT_DASH)
        while True:
            self._draw()
            bar.draw(self.stdscr)
            curses.curs_set(0)
            self.stdscr.refresh()
            ch = read_key(self.stdscr)
            if ch == CTRL_HOME:
                return None
            choice = bar.key(ch)
            if choice is None:
                continue
            if choice == -1:
                return None
            if choice == 0:
                self._goto(len(self.rows) - 1)
            elif choice == 1:
                self._goto(0)
            elif choice == 2:
                self._field_number()
            elif choice == 3:
                return "save"
            elif choice == 4:
                return "abandon"
            return None

    def _field_number(self):
        edit = LineEdit(str(self.row + 1), 3)
        while True:
            self._draw(f"Enter field #: {edit.text}")
            curses.curs_set(1)
            try:
                self.stdscr.move(0, 15 + edit.pos)
            except curses.error:
                pass
            ch = read_key(self.stdscr)
            result = edit.key(ch) if ch is not None else None
            if result == "cancel":
                return
            if result == "enter":
                text = edit.text.strip()
                if text.isdigit() and 1 <= int(text) <= len(self.rows):
                    self._goto(int(text) - 1)
                    return
                screen.error_wait(self.stdscr, read_key,
                                  f"Range is 1 to {len(self.rows)} (press SPACE)")
                return

    # ---------------------------------------------------------- gravar
    def _fields(self):
        fields = []
        for row in self.rows:
            if not row["name"]:
                continue
            fields.append({"name": row["name"], "type": row["type"],
                           "length": int(row["width"]),
                           "decimals": int(row["dec"]) if row["type"] == "N" else 0,
                           "orig": row["orig"]})
        return fields

    def _save(self):
        if not self._leave():
            return None
        fields = self._fields()
        if not fields:
            screen.error_wait(self.stdscr, read_key, "Empty structure will not be saved")
            return None
        for row in self.rows:
            if row["name"] and row["type"] in ("C", "N") and not row["width"]:
                screen.error_wait(self.stdscr, read_key, "Illegal data length")
                return None
        consequence = ""
        self.positional = False
        if self.modify:
            old = self.existing
            renamed = any(f["orig"] is not None and old.fields[f["orig"]]["name"] != f["name"]
                          for f in fields)
            if renamed:
                self._draw()
                screen.message(self.stdscr, "", 1)
                screen.message(self.stdscr,
                               "Should data be COPIED from backup for all fields? (Y/N) ", 2)
                ch = screen.wait_key(self.stdscr, read_key)
                self.positional = isinstance(ch, str) and ch.upper() == "Y"
                consequence = ("Database records will be COPIED from backup for all fields."
                               if self.positional else
                               "Database records will be APPENDED from backup fields of "
                               "the same name only!!")
        self._draw()
        screen.message(self.stdscr, consequence, 1)
        if not screen.wait_enter(self.stdscr, read_key,
                                 "Press ENTER to confirm.  Any other key to resume."):
            return None
        create_fields = [{k: v for k, v in f.items() if k != "orig"} for f in fields]
        try:
            if not self.modify:
                dbf = DBF.create(self.path, copy.deepcopy(create_fields))
                self._draw()
                screen.message(self.stdscr, "", 1)
                self.input_now = screen.ask_yn(self.stdscr, read_key,
                                               "Input data records now? (Y/N) ")
                return dbf
            return self._restructure(fields, create_fields)
        except (OSError, DBFError) as exc:
            screen.error_wait(self.stdscr, read_key, str(exc))
            return None

    def _restructure(self, fields, create_fields):
        old = self.existing
        positional = self.positional
        self._draw()
        screen.messages(self.stdscr, "", "Please wait ...")
        self.stdscr.refresh()

        if positional:
            sources = [i if i < len(old.fields) else None for i in range(len(fields))]
        else:
            sources = [old.field_index(f["name"]) if old.field_index(f["name"]) >= 0 else None
                       for f in fields]

        backup = self.path.with_suffix(".bak" if self.path.suffix.islower() else ".BAK")
        shutil.copy2(self.path, backup)
        old_memo = old.memo_path if old.memo_path.exists() else None
        if old_memo:
            shutil.copy2(old_memo, old_memo.with_suffix(
                ".tbk" if old_memo.suffix.islower() else ".TBK"))
        new = DBF.create(self.path, copy.deepcopy(create_fields), allow_memo=bool(old_memo))
        for rec_index, record in enumerate(old.records):
            values = []
            for field, orig in zip(new.fields, sources):
                if orig is None:
                    values.append("")
                    continue
                old_field = old.fields[orig]
                raw = record["values"][orig]
                if field["type"] == "M":
                    values.append(raw if old_field["type"] == "M" else "")
                    continue
                try:
                    if old_field["type"] == field["type"]:
                        values.append(new.validate(field, raw))
                    else:
                        values.append(new.from_typed(field, old.typed_value(rec_index, orig)))
                except (DBFError, ValueError):
                    values.append("")
            new.records.append({"deleted": record["deleted"], "values": values})
        new.save()
        if settings.on("TALK"):
            self.app.console.println(f"{len(new.records):7d} records added")
        return new

    # ------------------------------------------------------------ loop
    def _type_key(self, ch):
        row = self.rows[self.row]
        if ch == " ":
            row["type"] = TYPES[(TYPES.index(row["type"]) + 1) % len(TYPES)]
            return
        if isinstance(ch, str) and ch.upper() in TYPES:
            row["type"] = ch.upper()
            self._next()
            return
        if isinstance(ch, str):
            screen.error_wait(self.stdscr, read_key, "Field type must be C, N, D, L or M.")

    def _text_key(self, ch):
        edit = self.edit
        width = CELL_W[self.col]
        if isinstance(ch, str):
            if self.col == "name":
                ch = ch.upper()
            elif not ch.isdigit():
                curses.beep()
                return
            if self.col != "name" and not edit.dirty:
                edit.set("")
            if self.app.insert_mode or edit.pos >= len(edit.text):
                if len(edit.text) >= width:
                    curses.beep()
                    return
                edit.text = edit.text[:edit.pos] + ch + edit.text[edit.pos:]
            else:
                edit.text = edit.text[:edit.pos] + ch + edit.text[edit.pos + 1:]
            edit.pos += 1
            edit.dirty = True
            if edit.pos >= width:
                curses.beep()
                self._next()
            return
        if ch == 25:  # ^Y apaga
            edit.set("")
            edit.dirty = True
            return
        if ch == curses.KEY_LEFT and edit.pos == 0:
            self._prev()
            return
        if ch == curses.KEY_RIGHT and edit.pos >= len(edit.text):
            self._next()
            return
        if is_backspace(ch) or ch == curses.KEY_DC:
            edit.dirty = True
        edit.key(ch)

    def run(self):
        """Retorna o DBF criado/alterado ou None se abandonado."""
        while True:
            self._draw()
            ch = read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            action = None
            if ch == curses.KEY_F1:
                self.app.show_help = not self.app.show_help
            elif ch == curses.KEY_IC:
                self.app.insert_mode = not self.app.insert_mode
            elif ch == 27:
                action = "abandon"
            elif ch in (CTRL_END, 23):
                action = "save"
            elif ch == CTRL_HOME:
                action = self._menu()
            elif ch == 14:  # ^N insere campo
                if not self._leave():
                    continue
                if len(self.rows) >= MAX_FIELDS:
                    screen.error_wait(self.stdscr, read_key, "Maximum number of fields exceeded.")
                    continue
                self.rows.insert(self.row, _blank_row())
                self.col = "name"
                self._start_cell()
            elif ch == 21:  # ^U remove campo
                if len(self.rows) > 1:
                    del self.rows[self.row]
                    self.row = min(self.row, len(self.rows) - 1)
                else:
                    self.rows[0] = _blank_row()
                self.col = "name"
                self._start_cell()
            elif ch == curses.KEY_UP:
                self._goto(self.row - 1 if self.row else 0, self.col)
            elif ch == curses.KEY_DOWN:
                self._goto(self.row + 1, self.col)
            elif ch == curses.KEY_PPAGE:
                self._goto(max(0, self.row - 10))
            elif ch == curses.KEY_NPAGE:
                self._goto(min(len(self.rows) - 1, self.row + 10))
            elif is_enter(ch) or ch == 9:
                action = self._next()
            elif ch == curses.KEY_BTAB:
                self._prev()
            elif self.col == "type":
                if ch == curses.KEY_LEFT:
                    self._prev()
                elif ch == curses.KEY_RIGHT:
                    self._next()
                else:
                    self._type_key(ch)
            else:
                self._text_key(ch)

            if action == "abandon":
                self._draw()
                screen.message(self.stdscr, "", 1)
                if screen.ask_yn(self.stdscr, read_key, screen.MSG_ABANDON):
                    return None
            elif action == "save":
                result = self._save()
                if result is not None:
                    return result


def create_structure(app, path):
    """Retorna (dbf, responder 'Input data records now?') ou (None, False)."""
    editor = StructureEditor(app, path)
    dbf = editor.run()
    return dbf, getattr(editor, "input_now", False)


def modify_structure(app):
    dbf = app.current_dbf
    return StructureEditor(app, dbf.filename, existing=dbf).run()
