import curses
import os
from pathlib import Path

from . import APP_VERSION, runner, screen, ui, widgets
from .browser import Browser
from .form import append_records, edit_record
from .structure import create_structure, modify_structure
from .command import CommandWindow
from .dbf import DBF, DBFError
from .editor import Editor


class FoxBaseApp:
    def __init__(self, stdscr, args=None):
        self.stdscr = stdscr
        self.running = True
        self.view = "command"
        self.args = args or []

        self.current_dbf = None
        self.current_dbf_path = None
        self.current_record = 0
        self.eof = False
        self.memvars = {}
        self.insert_mode = False  # Ins: sobrescrever (padrão) / inserir
        self.show_help = True     # F1: caixa de ajuda das telas cheias

        ui.init_colors()
        curses.noecho()
        curses.raw()
        stdscr.keypad(True)
        try:
            curses.set_escdelay(25)
        except AttributeError:
            pass

        self.command = CommandWindow(self)
        self.browser = Browser(self)
        self.editor = Editor(self)
        self.status = "Ready"

        self.menubar = ui.MenuBar(
            self,
            [
                ("System", [
                    ("About FoxBASE+", self.about),
                    ("Keyboard help", self.help),
                    ("Quit", self.quit, "^Q"),
                ]),
                ("File", [
                    ("Use database...", self.open_dbf_prompt, "F2"),
                    ("Create database...", lambda: self.create_dbf(None)),
                    ("Modify structure", self.modify_structure),
                    ("Close database", self.close_dbf),
                    ("Open program...", self.open_program_prompt),
                    ("New program", self.new_program),
                    ("Save program", self.save_program),
                    ("Directory", lambda: self.command.execute("DIR")),
                ]),
                ("Database", [
                    ("Browse", self.browse, "F3"),
                    ("Edit record", self.edit_current),
                    ("Structure", self.structure, "F4"),
                    ("Append record", lambda: self.append_blank(edit=True), "F9"),
                    ("List", lambda: self.command.execute("LIST")),
                ]),
                ("Record", [
                    ("Go top", lambda: self.goto(1)),
                    ("Go bottom", lambda: self.goto(self.current_dbf.record_count
                                                    if self.current_dbf else 1)),
                    ("Delete", self.delete_current),
                    ("Recall", self.recall_current),
                    ("Pack", self.pack),
                ]),
                ("Program", [
                    ("Modify command", self.show_editor, "F7"),
                    ("Run current", self.run_program, "F5"),
                    ("Do program...", self.do_program_prompt),
                    ("Run shell command...", self.run_shell_prompt),
                ]),
                ("Window", [
                    ("Command", self.show_command, "F6"),
                    ("Browse", self.browse, "F3"),
                    ("Editor", self.show_editor, "F7"),
                ]),
            ],
        )

    # ------------------------------------------------------------ util
    def put(self, y, x, text, attr=0):
        ui.put(self.stdscr, y, x, text, attr)

    def ask(self, label, default=""):
        self.draw()
        value = widgets.prompt(self.stdscr, label, default)
        return value.strip() if value is not None else None

    def error(self, text):
        self.draw()
        widgets.message(self.stdscr, text, "Error", error=True)

    # ------------------------------------------------------------ loop
    def run(self):
        self._splash()
        for arg in self.args:
            if arg.lower().endswith(".prg"):
                self.modify_command(arg)
            else:
                self.command.execute(f"USE {arg}")

        while self.running:
            self.draw()
            ch = widgets.read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            self.key(ch)

    def _splash(self):
        h, w = self.stdscr.getmaxyx()
        ui.clear(self.stdscr)
        curses.curs_set(0)
        top = max(0, h // 2 - 6)
        ui.box(self.stdscr, top, max(0, (w - 50) // 2), 11, min(w, 50))
        ui.centered(self.stdscr, top + 2, "FoxBASE+", curses.A_BOLD)
        ui.centered(self.stdscr, top + 3, "Version 2.10 (Linux)")
        ui.centered(self.stdscr, top + 5, "(c) 1987-1991 Fox Software")
        ui.centered(self.stdscr, top + 6, "Terminal compatibility environment")
        ui.centered(self.stdscr, top + 8, " Press any key ", curses.color_pair(ui.C_REVERSE))
        self.stdscr.refresh()
        widgets.read_key(self.stdscr)

    def draw(self):
        ui.clear(self.stdscr)
        h, w = self.stdscr.getmaxyx()

        if w < 80 or h < 24:
            ui.centered(self.stdscr, h // 2, f"Terminal must be at least 80x24 ({w}x{h}).")
            self.stdscr.refresh()
            return

        self.menubar.draw(self.stdscr)

        cursor = None
        if self.view == "command":
            ui.box(self.stdscr, 1, 0, h - 2, w, "Command")
            cursor = self.command.draw(self.stdscr)
        elif self.view == "editor":
            ui.box(self.stdscr, 1, 0, h - 2, w, self.editor.title)
            cursor = self.editor.draw(self.stdscr)

        self._status()

        if self.menubar.active:
            self.menubar.popup(self.stdscr)
            cursor = None

        if cursor:
            curses.curs_set(1)
            try:
                self.stdscr.move(*cursor)
            except curses.error:
                pass
        else:
            curses.curs_set(0)
        self.stdscr.refresh()

    def _status(self):
        h, w = self.stdscr.getmaxyx()
        attr = curses.color_pair(ui.C_STATUS)
        ui.fill(self.stdscr, h - 1, 0, w, " ", attr)

        right = ""
        if self.current_dbf:
            db = self.current_dbf
            rec = "EOF" if self.eof or not db.record_count else str(self.current_record + 1)
            right = f"{db.filename.name.upper()}  Rec {rec}/{db.record_count}"
        left = f" {self.view.upper():<8}│ {self.status}"
        ui.put(self.stdscr, h - 1, 0, left[:w - len(right) - 4], attr)
        ui.put(self.stdscr, h - 1, max(0, w - len(right) - 2), right, attr | curses.A_BOLD)

    # ------------------------------------------------------------ keys
    def key(self, ch):
        if self.menubar.active:
            action = self.menubar.key(ch)
            if action:
                action()
            return

        if ch == curses.KEY_F10:
            self.menubar.open()
            return
        if ch == 17:  # Ctrl-Q
            self.quit()
            return

        # no editor F2/F5 pertencem a ele
        if self.view == "editor" and ch in (curses.KEY_F2, curses.KEY_F5):
            self.editor.key(ch)
            return

        global_keys = {
            curses.KEY_F1: self.help,
            curses.KEY_F2: self.open_dbf_prompt,
            curses.KEY_F3: self.browse,
            curses.KEY_F4: self.structure,
            curses.KEY_F5: self.run_program,
            curses.KEY_F6: self.show_command,
            curses.KEY_F7: self.show_editor,
            curses.KEY_F9: lambda: self.append_blank(edit=True),
        }
        if ch in global_keys:
            global_keys[ch]()
            return

        if self.view == "command":
            self.command.key(ch)
        elif self.view == "editor":
            self.editor.key(ch)

    # ----------------------------------------------------------- views
    def show_command(self):
        self.view = "command"
        self.status = "Ready"

    def show_editor(self):
        self.view = "editor"
        self.status = "Modify Command"

    def browse(self):
        if not self.current_dbf:
            self.command.write("No database is in use.")
            self.show_command()
            return
        self.show_command()
        self.browser.run()
        self.stdscr.clear()

    # -------------------------------------------------------- database
    def _resolve_dbf(self, filename):
        path = Path(filename).expanduser()
        if not path.suffix:
            path = path.with_suffix(".dbf")
        if not path.exists():
            # procura ignorando maiúsc./minúsc. (DBFs vindos do DOS)
            parent = path.parent if str(path.parent) else Path(".")
            if parent.is_dir():
                for candidate in parent.iterdir():
                    if candidate.name.lower() == path.name.lower():
                        return candidate.resolve()
        return path.resolve()

    def open_dbf_prompt(self):
        name = self.ask("USE - database file name:", "")
        if name:
            self.show_command()
            self.command.execute(f"USE {name}")

    def open_dbf(self, filename):
        path = self._resolve_dbf(filename)
        try:
            dbf = DBF(path)
        except FileNotFoundError:
            self.command.write(f"File does not exist: {path.name}")
            return
        except (OSError, DBFError) as exc:
            self.command.write(f"Error: {exc}")
            return

        self.current_dbf = dbf
        self.current_dbf_path = str(path)
        self.current_record = 0
        self.eof = dbf.record_count == 0
        self.browser.reset()
        self.status = f"{path.name} ({dbf.record_count} records, {dbf.codepage})"

    def close_dbf(self):
        self.current_dbf = None
        self.current_dbf_path = None
        self.current_record = 0
        self.eof = False
        self.status = "Ready"

    def create_dbf(self, filename):
        self.show_command()
        if not filename:
            filename = self.ask("CREATE - new database file name:", "")
            if not filename:
                return
        path = Path(filename).expanduser()
        if not path.suffix:
            path = path.with_suffix(".dbf")
        if path.exists():
            self.draw()
            if not widgets.confirm(self.stdscr, f"{path.name} already exists. Overwrite?"):
                return
        dbf = create_structure(self, path)
        self.stdscr.clear()
        if dbf is None:
            return
        self.open_dbf(str(path))
        self.draw()
        if screen.ask_yn(self.stdscr, widgets.read_key, "Input data records now? (Y/N)"):
            append_records(self)
            self.stdscr.clear()

    def modify_structure(self):
        if not self.current_dbf:
            self.command.write("No database is in use.")
            return
        self.show_command()
        dbf = modify_structure(self)
        self.stdscr.clear()
        if dbf is None:
            return
        self.open_dbf(str(dbf.filename))
        self.command.write(f"{dbf.filename.name} modified (backup in .BAK).")

    def structure(self):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            self.show_command()
            return
        self.show_command()
        self.command.write(f"Structure for database : {db.filename}")
        self.command.write(f"Number of data records : {db.record_count:>8}")
        self.command.write(f"Codepage               : {db.codepage:>8}")
        self.command.write("Field  Field Name  Type       Width   Dec")
        type_names = {"C": "Character", "N": "Numeric", "F": "Float", "D": "Date",
                      "L": "Logical", "M": "Memo"}
        for i, field in enumerate(db.fields, 1):
            dec = field["decimals"] if field["type"] in ("N", "F") else ""
            self.command.write(
                f"{i:>5}  {field['name']:<10}  {type_names.get(field['type'], field['type']):<10}"
                f" {field['length']:>5}  {dec:>4}")
        self.command.write(f"** Total **                     {db.record_length:>5}")

    def edit_current(self, mode="EDIT"):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        if not db.record_count or self.eof:
            self.command.write("End of file encountered.")
            return
        edit_record(self, self.current_record, mode)
        self.stdscr.clear()

    def goto(self, number, quiet=False):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        if not db.record_count:
            self.eof = True
            return
        if not 1 <= number <= db.record_count:
            self.command.write("Record is out of range.")
            return
        self.current_record = number - 1
        self.eof = False

    def skip(self, count):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        target = self.current_record + count
        if self.eof and count < 0:
            target = db.record_count + count
        if target >= db.record_count:
            self.current_record = max(0, db.record_count - 1)
            self.eof = True
            self.command.write("End of file encountered.")
        elif target < 0:
            self.current_record = 0
            self.eof = False
            self.command.write("Beginning of file encountered.")
        else:
            self.current_record = target
            self.eof = False
            self.command.write(f"Record No. {target + 1:>7}")

    def append_blank(self, edit=False):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        if edit:  # APPEND: tela cheia; só grava registros preenchidos
            self.show_command()
            append_records(self)
            self.stdscr.clear()
            return
        try:
            index = db.append_blank()
        except DBFError as exc:
            self.error(str(exc))
            return
        self.current_record = index
        self.eof = False
        self.status = f"Record {index + 1} appended."

    def delete_current(self):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        if not db.record_count or self.eof:
            self.command.write("End of file encountered.")
            return
        db.delete(self.current_record)
        self.command.write("1 record deleted")

    def recall_current(self):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        if not db.record_count or self.eof:
            self.command.write("End of file encountered.")
            return
        db.recall(self.current_record)
        self.command.write("1 record recalled")

    def pack(self):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        removed = db.pack()
        self.current_record = 0
        self.eof = db.record_count == 0
        self.command.write(f"{db.record_count} records copied, {removed} removed.")
        self.status = "PACK complete."

    def zap(self):
        db = self.current_dbf
        if not db:
            self.command.write("No database is in use.")
            return
        self.draw()
        if widgets.confirm(self.stdscr, f"Zap {db.filename.name}? All records will be lost"):
            db.zap()
            self.current_record = 0
            self.eof = True
            self.command.write("Zap complete.")

    # --------------------------------------------------------- programs
    def new_program(self):
        if self.editor.modified and not self._confirm_discard():
            return
        self.editor.__init__(self)
        self.show_editor()

    def _confirm_discard(self):
        self.draw()
        return widgets.confirm(self.stdscr, "Program not saved. Discard changes?")

    def modify_command(self, filename=None):
        if filename:
            if self.editor.modified and not self._confirm_discard():
                return
            self.editor.load(filename.strip('"\''))
        self.view = "editor"

    def open_program_prompt(self):
        name = self.ask("MODIFY COMMAND - program file:", "")
        if name:
            self.modify_command(name)

    def save_program(self):
        self.editor.save()

    def run_program(self):
        self.editor.run()

    def do_program(self, filename):
        path = Path(filename.strip('"\'')).expanduser()
        if not path.suffix:
            path = path.with_suffix(".prg")
        if not path.exists():
            self.command.write(f"File does not exist: {path.name}")
            return
        self.show_command()
        runner.compile_and_run(self, path)

    def do_program_prompt(self):
        name = self.ask("DO - program file:", "")
        if name:
            self.show_command()
            self.command.execute(f"DO {name}")

    def run_shell(self, command):
        if not command:
            command = os.environ.get("SHELL", "/bin/sh")
        code = runner.run_in_terminal(self, command, shell=True)
        self.command.write(f"Exit: {code}")

    def run_shell_prompt(self):
        cmd = self.ask("RUN - shell command (empty = interactive shell):", "")
        if cmd is not None:
            self.show_command()
            self.command.execute(f"RUN {cmd}" if cmd else "RUN")

    # ------------------------------------------------------------- misc
    def about(self):
        self.draw()
        widgets.message(
            self.stdscr,
            f"FoxBASE Linux {APP_VERSION}\n"
            "FoxBASE+ 2.10 terminal compatibility environment\n\n"
            "Python curses frontend, native DBF engine,\n"
            "Harbour (hbmk2) backend for PRG programs.",
            "About",
        )

    def help(self):
        self.show_command()
        self.command.write(self.command_help())

    @staticmethod
    def command_help():
        from .command import HELP_TEXT
        return HELP_TEXT

    def quit(self):
        if self.editor.modified:
            self.draw()
            if not widgets.confirm(self.stdscr, "Program not saved. Quit anyway?"):
                return
        self.running = False
