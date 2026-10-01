"""CREATE / MODIFY STRUCTURE em tela cheia, no estilo dBASE III PLUS / FoxBASE+.

- Campos em duas colunas: Field Name, Type, Width, Dec; "Bytes remaining" no topo.
- Tipo: barra de espaço alterna (Character, Numeric, Date, Logical) ou a letra inicial.
- Date e Logical têm largura fixa (8 e 1); Dec só existe no Numeric.
- ^N insere campo, ^U remove campo, ^End grava ("Press ENTER to confirm. Any other
  key to resume"), Esc abandona. Enter num nome em branco no fim também grava.
- MODIFY STRUCTURE guarda o original em .BAK e copia os dados pelos nomes dos campos.
"""

import copy
import curses
import shutil
from pathlib import Path

from . import screen, ui
from .dbf import DBF, DBFError
from .widgets import CTRL_END, is_backspace, is_enter, read_key

MAX_RECORD = 4000
MAX_FIELDS = 128
TYPE_NAMES = {"C": "Character", "N": "Numeric", "D": "Date", "L": "Logical", "M": "Memo"}
TYPE_CYCLE = ["C", "N", "D", "L"]
COLUMNS = ("name", "type", "width", "dec")
COLUMN_WIDTH = {"name": 10, "type": 9, "width": 3, "dec": 3}

MESSAGES = {
    "name": ("Enter the field name.",
             "Field names begin with a letter and may contain letters, digits and underscores"),
    "type": ("Enter the field type.",
             "Press SPACE to change, or type C, N, D or L"),
    "width": ("Enter the field width.",
              "Character fields: 1-254  Numeric fields: 1-19"),
    "dec": ("Enter the number of decimal places.",
            "Decimals must be less than the width minus 1"),
}


def _blank_row():
    return {"name": "", "type": "C", "width": "", "dec": "", "orig": None}


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
                self.rows.append({
                    "name": field["name"],
                    "type": field["type"],
                    "width": str(field["length"]),
                    "dec": str(field["decimals"]) if field["type"] in ("N", "F") else "",
                    "orig": index,
                })
        if not self.rows:
            self.rows.append(_blank_row())
        self.row = 0
        self.col = "name"
        self.pos = 0
        self.page_top = 0
        self.msg = ""
        self.msg_error = False

    # ------------------------------------------------------------ regras
    @staticmethod
    def _fixed_width(kind):
        return {"D": "8", "L": "1", "M": "10"}.get(kind)

    def _columns_for(self, row):
        kind = row["type"]
        if kind in ("D", "L", "M"):
            return ["name", "type"]
        if kind in ("N", "F"):
            return ["name", "type", "width", "dec"]
        return ["name", "type", "width"]

    def _bytes_used(self):
        total = 1
        for row in self.rows:
            width = self._fixed_width(row["type"]) or row["width"]
            if str(width).isdigit():
                total += int(width)
        return total

    def _validate_row(self, row, index):
        name = row["name"].strip().upper()
        if not name:
            return "Field name is required."
        if not name[0].isalpha() or not all(c.isalnum() or c == "_" for c in name):
            return "Field names begin with a letter and may contain letters, digits and underscores"
        for other_index, other in enumerate(self.rows):
            if other_index != index and other["name"].strip().upper() == name:
                return f"Field name already exists: {name}"
        kind = row["type"]
        if kind in ("C", "N", "F"):
            if not row["width"].strip().isdigit():
                return "Field width is required."
            width = int(row["width"])
            if kind == "C" and not 1 <= width <= 254:
                return "Illegal value: width must be 1-254"
            if kind in ("N", "F") and not 1 <= width <= 19:
                return "Illegal value: width must be 1-19"
            if kind in ("N", "F") and row["dec"].strip():
                dec = int(row["dec"]) if row["dec"].strip().isdigit() else -1
                if dec < 0 or (dec > 0 and dec > width - 2) or dec > 15:
                    return "Illegal value: decimals"
        return None

    def _row_complete(self, row):
        return bool(row["name"].strip())

    # ------------------------------------------------------- navegação
    def _cell(self):
        row = self.rows[self.row]
        value = row[self.col]
        if self.col == "type":
            return TYPE_NAMES.get(value, value)
        return value

    def _leave_row(self):
        """Valida a linha atual ao sair dela. Linha toda vazia no fim é descartada."""
        row = self.rows[self.row]
        if not self._row_complete(row) and self.row == len(self.rows) - 1 \
                and not row["width"].strip():
            return True
        error = self._validate_row(row, self.row)
        if error:
            self._error(error)
            return False
        row["name"] = row["name"].strip().upper()
        if not row["dec"].strip() and row["type"] in ("N", "F"):
            row["dec"] = "0"
        return True

    def _move_row(self, target, col="name"):
        if target == self.row:
            return
        if not self._leave_row():
            return
        current = self.row
        if target >= len(self.rows):
            if not self._row_complete(self.rows[current]):
                return
            if len(self.rows) >= MAX_FIELDS:
                self._error(f"Maximum of {MAX_FIELDS} fields.")
                return
            self.rows.append(_blank_row())
            target = len(self.rows) - 1
        elif (current == len(self.rows) - 1 and len(self.rows) > 1
              and not self._row_complete(self.rows[current])):
            self.rows.pop()  # linha nova em branco no fim é descartada
        self.row = max(0, min(target, len(self.rows) - 1))
        self.col = col
        self.pos = 0

    def _next_col(self):
        row = self.rows[self.row]
        cols = self._columns_for(row)
        if self.col == "name" and not row["name"].strip():
            if self.row == len(self.rows) - 1:
                return "finish"
            self._error("Field name is required.")
            return None
        if self.col == "name":
            error = None
            name = row["name"].strip().upper()
            if not name[0].isalpha() or not all(c.isalnum() or c == "_" for c in name):
                error = MESSAGES["name"][1]
            if error:
                self._error(error)
                return None
            row["name"] = name
        index = cols.index(self.col) if self.col in cols else len(cols) - 1
        if index + 1 < len(cols):
            self.col = cols[index + 1]
            self.pos = 0
            return None
        self._move_row(self.row + 1)
        return None

    def _prev_col(self):
        cols = self._columns_for(self.rows[self.row])
        index = cols.index(self.col) if self.col in cols else 0
        if index > 0:
            self.col = cols[index - 1]
            self.pos = 0
        elif self.row > 0:
            target = self.row - 1
            self._move_row(target, col="name")
            if self.row == target:
                self.col = self._columns_for(self.rows[self.row])[-1]

    def _error(self, text):
        curses.beep()
        self.msg = text
        self.msg_error = True

    # ------------------------------------------------------------ edição
    def _type_key(self, ch):
        row = self.rows[self.row]
        if ch == " ":
            cycle = TYPE_CYCLE + (["M"] if row["type"] == "M" or
                                  (row["orig"] is not None and self.existing and
                                   self.existing.fields[row["orig"]]["type"] == "M") else [])
            current = cycle.index(row["type"]) if row["type"] in cycle else 0
            row["type"] = cycle[(current + 1) % len(cycle)]
        elif isinstance(ch, str) and ch.upper() in TYPE_CYCLE:
            row["type"] = ch.upper()
        else:
            curses.beep()
            return
        fixed = self._fixed_width(row["type"])
        if fixed:
            row["width"], row["dec"] = fixed, ""
        elif row["type"] == "C":
            row["dec"] = ""
        if ch != " ":
            self._next_col()

    def _text_key(self, ch):
        row = self.rows[self.row]
        limit = COLUMN_WIDTH[self.col]
        text = row[self.col]
        if isinstance(ch, str):
            if self.col == "name":
                ch = ch.upper()
                if not (ch.isalnum() or ch == "_") or ord(ch) > 127:
                    curses.beep()
                    return
                if not text and not ch.isalpha():
                    self._error(MESSAGES["name"][1])
                    return
            elif not ch.isdigit():
                curses.beep()
                return
            if self.app.insert_mode:
                text = (text[:self.pos] + ch + text[self.pos:])[:limit]
            else:
                text = text[:self.pos] + ch + text[self.pos + 1:]
            row[self.col] = text[:limit]
            self.pos += 1
            if self.pos >= limit:
                curses.beep()
                self._next_col()
        elif ch == curses.KEY_LEFT:
            if self.pos > 0:
                self.pos -= 1
            else:
                self._prev_col()
        elif ch == curses.KEY_RIGHT:
            if self.pos < min(len(text), limit - 1):
                self.pos += 1
            else:
                self._next_col()
        elif ch == curses.KEY_HOME:
            self.pos = 0
        elif ch == curses.KEY_END:
            self.pos = min(len(text), limit - 1)
        elif is_backspace(ch):
            if self.pos > 0:
                row[self.col] = text[:self.pos - 1] + text[self.pos:]
                self.pos -= 1
        elif ch == curses.KEY_DC:
            row[self.col] = text[:self.pos] + text[self.pos + 1:]
        elif ch == 25:  # ^Y
            row[self.col] = text[:self.pos]

    # ------------------------------------------------------------ gravar
    def _fields(self):
        fields = []
        for index, row in enumerate(self.rows):
            if not self._row_complete(row):
                continue
            error = self._validate_row(row, index)
            if error:
                self.row, self.col = index, "name"
                self._error(error)
                return None
            kind = row["type"]
            fields.append({
                "name": row["name"].strip().upper(),
                "type": kind,
                "length": int(self._fixed_width(kind) or row["width"]),
                "decimals": int(row["dec"] or 0) if kind in ("N", "F") else 0,
                "orig": row["orig"],
            })
        if not fields:
            self._error("Database has no fields.")
            return None
        if sum(f["length"] for f in fields) + 1 > MAX_RECORD:
            self._error(f"Record too long (maximum {MAX_RECORD} bytes).")
            return None
        return fields

    def _save(self):
        fields = self._fields()
        if fields is None:
            return None
        if not screen.wait_enter(self.stdscr, read_key,
                                 "Press ENTER to confirm. Any other key to resume"):
            return None
        create_fields = [{k: v for k, v in f.items() if k != "orig"} for f in fields]
        try:
            if not self.modify:
                return DBF.create(self.path, copy.deepcopy(create_fields))
            return self._restructure(fields, create_fields)
        except (OSError, DBFError) as exc:
            self._error(f"Error: {exc}")
            return None

    def _restructure(self, fields, create_fields):
        old = self.existing
        backup = self.path.with_suffix(".bak" if self.path.suffix.islower() else ".BAK")
        shutil.copy2(self.path, backup)
        new = DBF.create(self.path, copy.deepcopy(create_fields), allow_memo=True)
        for rec_index, record in enumerate(old.records):
            values = []
            for field, spec in zip(new.fields, fields):
                orig = spec["orig"]
                if orig is None:
                    values.append("")
                    continue
                old_field = old.fields[orig]
                raw = record["values"][orig]
                if old_field["type"] == field["type"] == "M":
                    values.append(raw)
                    continue
                try:
                    if old_field["type"] == field["type"]:
                        values.append(new.validate(field, raw if field["type"] != "D"
                                                   else (raw or "")))
                    else:
                        values.append(new.from_typed(field, old.typed_value(
                            rec_index, orig)))
                except (DBFError, ValueError):
                    values.append("")
            new.records.append({"deleted": record["deleted"], "values": values})
        new.save()
        return new

    # -------------------------------------------------------------- tela
    def _draw(self):
        stdscr = self.stdscr
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        y = 0
        if self.app.show_help:
            y = screen.help_box(stdscr, screen.HELP_CREATE)
        remaining = f"Bytes remaining: {MAX_RECORD - self._bytes_used():>6}"
        ui.put(stdscr, y + 1, w - len(remaining) - 2, remaining)
        header = "Field Name  Type       Width   Dec"
        col_x = (6, 6 + (w // 2))
        ui.put(stdscr, y + 2, col_x[0], header, curses.A_BOLD)
        ui.put(stdscr, y + 2, col_x[1], header, curses.A_BOLD)
        first = y + 3
        per_col = max(1, h - 3 - first)
        per_page = per_col * 2

        if self.row < self.page_top:
            self.page_top = (self.row // per_page) * per_page
        elif self.row >= self.page_top + per_page:
            self.page_top = (self.row // per_page) * per_page

        cursor = None
        rev = curses.color_pair(ui.C_REVERSE)
        for slot in range(per_page):
            index = self.page_top + slot
            if index >= len(self.rows):
                break
            row = self.rows[index]
            x = col_x[slot // per_col] - 5
            yy = first + slot % per_col
            ui.put(stdscr, yy, x, f"{index + 1:>4}")
            cols = self._columns_for(row)
            cells = {
                "name": (x + 5, row["name"].ljust(10)),
                "type": (x + 17, TYPE_NAMES.get(row["type"], row["type"]).ljust(9)),
                "width": (x + 29, (self._fixed_width(row["type"]) or row["width"]).rjust(3)),
                "dec": (x + 37, row["dec"].rjust(3) if "dec" in cols else ""),
            }
            for col, (cx, text) in cells.items():
                if col == "dec" and "dec" not in cols:
                    continue
                if col == "width" and "width" not in cols:
                    ui.put(stdscr, yy, cx, text)  # largura fixa: só mostra
                    continue
                if index == self.row and col == self.col:
                    if col in ("width", "dec"):
                        text = row[col].ljust(3)
                    ui.put(stdscr, yy, cx, text, rev)
                    cursor = (yy, cx + (0 if col == "type" else min(self.pos, len(text) - 1)))
                else:
                    ui.put(stdscr, yy, cx, text, rev if index == self.row else 0)

        mode = "MODIFY STRU" if self.modify else "CREATE"
        screen.status_bar(stdscr, mode, self.path,
                          f"Field: {self.row + 1}/{len(self.rows)}",
                          screen.flags_text(self.app.insert_mode))
        if self.msg:
            screen.message(stdscr, self.msg, error=self.msg_error)
        else:
            top, bottom = MESSAGES[self.col]
            ui.put(stdscr, h - 3, max(0, (w - len(top)) // 2), top, curses.A_BOLD)
            screen.message(stdscr, bottom)
        if cursor:
            curses.curs_set(1)
            try:
                stdscr.move(*cursor)
            except curses.error:
                pass
        stdscr.refresh()

    # -------------------------------------------------------------- loop
    def run(self):
        """Retorna o DBF criado/alterado ou None se abandonado."""
        while True:
            self._draw()
            ch = read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            self.msg, self.msg_error = "", False

            if ch == curses.KEY_F1:
                self.app.show_help = not self.app.show_help
            elif ch == curses.KEY_IC:
                self.app.insert_mode = not self.app.insert_mode
            elif ch == 27:
                if screen.ask_yn(self.stdscr, read_key,
                                 "Are you sure you want to abandon operation? (Y/N)"):
                    return None
            elif ch in (CTRL_END, 23):  # ^End / ^W
                result = self._save()
                if result is not None:
                    return result
            elif ch == 14:  # ^N insere campo
                if len(self.rows) >= MAX_FIELDS:
                    self._error(f"Maximum of {MAX_FIELDS} fields.")
                else:
                    self.rows.insert(self.row, _blank_row())
                    self.col, self.pos = "name", 0
            elif ch == 21:  # ^U remove campo
                if len(self.rows) > 1:
                    del self.rows[self.row]
                    self.row = min(self.row, len(self.rows) - 1)
                else:
                    self.rows[0] = _blank_row()
                self.col, self.pos = "name", 0
            elif ch == curses.KEY_UP:
                self._move_row(self.row - 1 if self.row else 0, self.col
                               if self.col in ("name", "type") else "name")
            elif ch == curses.KEY_DOWN:
                if self.row < len(self.rows) - 1 or self._row_complete(self.rows[self.row]):
                    self._move_row(self.row + 1, self.col
                                   if self.col in ("name", "type") else "name")
            elif ch == curses.KEY_PPAGE:
                self._move_row(max(0, self.row - 10))
            elif ch == curses.KEY_NPAGE:
                self._move_row(min(len(self.rows) - 1, self.row + 10))
            elif is_enter(ch):
                if self._next_col() == "finish":
                    result = self._save()
                    if result is not None:
                        return result
            elif ch in (9,):
                self._next_col()
            elif ch == curses.KEY_BTAB:
                self._prev_col()
            elif self.col == "type":
                if ch in (curses.KEY_LEFT,):
                    self._prev_col()
                elif ch in (curses.KEY_RIGHT,):
                    self._next_col()
                else:
                    self._type_key(ch)
            else:
                self._text_key(ch)


def create_structure(app, path):
    return StructureEditor(app, path).run()


def modify_structure(app):
    dbf = app.current_dbf
    return StructureEditor(app, dbf.filename, existing=dbf).run()
