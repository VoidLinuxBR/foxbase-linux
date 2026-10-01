"""BROWSE: grade de registros."""

import curses

from . import ui
from .widgets import is_enter, record_editor


class Browser:
    def __init__(self, app):
        self.app = app
        self.top = 0
        self.left = 0  # primeiro campo visível (rolagem horizontal)

    @property
    def row(self):
        return self.app.current_record

    @row.setter
    def row(self, value):
        self.app.current_record = value
        self.app.eof = False

    def reset(self):
        self.top = 0
        self.left = 0

    def _columns(self, dbf, w):
        columns = []
        x = 3
        for field_index in range(self.left, len(dbf.fields)):
            field = dbf.fields[field_index]
            width = max(dbf.display_width(field), len(field["name"]))
            width = min(width, w - 6)
            if columns and x + width >= w - 2:
                break
            columns.append((field_index, x, field["name"], width))
            x += width + 1
        return columns

    def draw(self, stdscr):
        dbf = self.app.current_dbf
        if not dbf:
            return None

        h, w = stdscr.getmaxyx()
        ui.box(stdscr, 1, 0, h - 2, w, f"Browse: {dbf.filename.name.upper()}")

        columns = self._columns(dbf, w)
        for _, x, name, width in columns:
            ui.put(stdscr, 2, x, name[:width].ljust(width),
                   curses.color_pair(ui.C_MENU) | curses.A_BOLD)
            ui.put(stdscr, 3, x, "─" * width, curses.color_pair(ui.C_BORDER))

        visible = max(1, h - 7)
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + visible:
            self.top = self.row - visible + 1
        self.top = max(0, min(self.top, max(0, dbf.record_count - visible)))

        for screen_row in range(visible):
            index = self.top + screen_row
            if index >= dbf.record_count:
                break
            record = dbf.records[index]
            selected = index == self.row
            attr = curses.color_pair(ui.C_REVERSE) if selected else 0
            y = 4 + screen_row
            if selected:
                ui.fill(stdscr, y, 1, w - 2, " ", attr)
            ui.put(stdscr, y, 1, "*" if record["deleted"] else " ",
                   attr | curses.A_BOLD)
            for field_index, x, _, width in columns:
                field = dbf.fields[field_index]
                value = dbf.display_value(field, record["values"][field_index])
                if field["type"] in ("N", "F"):
                    value = value.rjust(width)
                ui.put(stdscr, y, x, value[:width].ljust(width), attr)

        if not dbf.record_count:
            ui.put(stdscr, 5, 4, "(no records - press F9 / Ctrl-N to append)")

        more = ""
        if self.left > 0:
            more += "◄"
        if columns and columns[-1][0] < len(dbf.fields) - 1:
            more += "►"
        footer = "↑↓ PgUp/PgDn  ←→ fields  Enter Edit  F9 Append  Ctrl-T Del  Esc"
        ui.put(stdscr, h - 3, 2, footer[:w - 8], curses.color_pair(ui.C_DISABLED))
        ui.put(stdscr, h - 3, w - 4, more)
        return None

    def key(self, ch):
        dbf = self.app.current_dbf
        if not dbf:
            return

        last = max(0, dbf.record_count - 1)
        page = max(1, self.app.stdscr.getmaxyx()[0] - 7)

        if ch == 27:
            self.app.show_command()
        elif ch == curses.KEY_UP:
            self.row = max(0, self.row - 1)
        elif ch == curses.KEY_DOWN:
            self.row = min(last, self.row + 1)
        elif ch == curses.KEY_PPAGE:
            self.row = max(0, self.row - page)
        elif ch == curses.KEY_NPAGE:
            self.row = min(last, self.row + page)
        elif ch == curses.KEY_HOME:
            self.row = 0
        elif ch == curses.KEY_END:
            self.row = last
        elif ch == curses.KEY_LEFT:
            self.left = max(0, self.left - 1)
        elif ch == curses.KEY_RIGHT:
            self.left = min(len(dbf.fields) - 1, self.left + 1)
        elif is_enter(ch):
            if dbf.record_count:
                if record_editor(self.app.stdscr, dbf, self.row, "Edit"):
                    self.app.status = f"Record {self.row + 1} saved."
        elif ch in (20, 21, curses.KEY_DC):  # Ctrl-T / Ctrl-U / Del
            if dbf.record_count:
                if dbf.records[self.row]["deleted"]:
                    dbf.recall(self.row)
                    self.app.status = "Record recalled."
                else:
                    dbf.delete(self.row)
                    self.app.status = "Record marked for deletion."
        elif ch == 14:  # Ctrl-N
            self.app.append_blank(edit=True)
