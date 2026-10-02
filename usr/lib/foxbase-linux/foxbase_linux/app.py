"""Janela principal: linha de comandos (ponto) do FoxBASE+ 2.10 com a barra de
menus do foxbase-linux por cima. Os menus só executam comandos do original."""

import curses
import os
from pathlib import Path

from . import APP_VERSION, runner, screen, settings, ui, widgets
from .browser import Browser
from .command import CommandWindow, CommandError
from .console import Console
from .dbf import DBF, DBFError
from .form import append_records, edit_record
from .structure import create_structure, modify_structure
from .editor import modify_command as edit_program
from .helpview import show_help

MENU_KEY = curses.KEY_F12  # F10 é EDIT no original; o menu fica no F12 / Alt+letra


class FoxBaseApp:
    def __init__(self, stdscr, args=None):
        self.stdscr = stdscr
        self.running = True
        self.args = args or []

        self.current_dbf = None
        self.current_dbf_path = None
        self.current_record = 0
        self.eof = False
        self.bof = False
        self.found = False
        self.memvars = {}
        self.insert_mode = False  # Ins
        self.show_help = True     # F1 nas telas cheias (caixa de navegação)
        self.mode_line = "Command Line"
        self.banner = f"foxbase-linux {APP_VERSION} - FoxBASE+ 2.10 compatible"

        ui.init_colors()
        curses.noecho()
        curses.raw()
        stdscr.keypad(True)
        try:
            curses.set_escdelay(25)
        except AttributeError:
            pass

        self.console = Console(self)
        self.command = CommandWindow(self)
        self.browser = Browser(self)

        cmd = self.menu_command
        typed = self.menu_type
        self.menubar = ui.MenuBar(self, [
            ("System", [
                ("Help", lambda: self.help(""), "F1"),
                ("Display status", cmd("display status"), "F6"),
                ("Display memory", cmd("display memory"), "F7"),
                ("Quit", cmd("QUIT")),
            ]),
            ("File", [
                ("Use...", typed("USE ")),
                ("Create...", typed("CREATE ")),
                ("Modify structure", cmd("MODIFY STRUCTURE")),
                ("Close databases", cmd("CLOSE DATABASES")),
                ("Dir", cmd("dir"), "F4"),
                ("Modify command...", typed("MODIFY COMMAND ")),
                ("Do...", typed("DO ")),
                ("Run...", typed("RUN ")),
            ]),
            ("Database", [
                ("Browse", cmd("BROWSE")),
                ("Edit", cmd("edit"), "F10"),
                ("Append", cmd("append"), "F9"),
                ("List", cmd("list"), "F3"),
                ("Display", cmd("display"), "F8"),
                ("Structure", cmd("display structure"), "F5"),
                ("Pack", cmd("PACK")),
                ("Zap", cmd("ZAP")),
            ]),
            ("Record", [
                ("Top", cmd("GO TOP")),
                ("Bottom", cmd("GO BOTTOM")),
                ("Goto...", typed("GOTO ")),
                ("Skip", cmd("SKIP")),
                ("Locate...", typed("LOCATE FOR ")),
                ("Continue", cmd("CONTINUE")),
                ("Delete", cmd("DELETE")),
                ("Recall", cmd("RECALL")),
            ]),
        ])

    # --------------------------------------------------------- menus
    def menu_command(self, text):
        def action():
            self.command.edit.set("")
            self.command.submit(text)
        return action

    def menu_type(self, text):
        def action():
            self.command.edit.set(text)
        return action

    def top_row(self):
        return 1  # linha 0: barra de menus

    # ------------------------------------------------------------ loop
    def run(self):
        self._splash()
        for arg in self.args:
            if arg.lower().endswith(".prg"):
                self.command.submit(f"MODIFY COMMAND {arg}")
            else:
                self.command.submit(f"USE {arg}")

        while self.running:
            self.draw(edit=self.command.edit)
            ch = widgets.read_key(self.stdscr)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            self.key(ch)

    def _splash(self):
        """Logotipo na área de comandos e o ponto embaixo, sem esperar tecla."""
        logo = [
            "",
            "  ######   #####   ##   ##  ######    ####    #####  #######       ##",
            "  ##      ##   ##   ## ##   ##   ##  ##  ##  ##      ##            ##",
            "  #####   ##   ##    ###    ######  ##    ##  ####   #####     ########",
            "  ##      ##   ##   ## ##   ##   ## ########     ##  ##            ##",
            "  ##       #####   ##   ##  ######  ##    ## #####   #######       ##",
            "",
            "",
            f"{'Linux terminal compatibility environment':^78}",
        ]
        self.console.lines = logo + ["", ""]
        self.console.col = 0
        self.console.prompt()
        self.banner_shown = True

    def draw(self, edit=None):
        ui.clear(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        if w < 80 or h < 24:
            ui.centered(self.stdscr, h // 2, f"Terminal must be at least 80x24 ({w}x{h}).")
            self.stdscr.refresh()
            return

        self.menubar.draw(self.stdscr)
        cursor = self.console.draw(self.stdscr, edit)
        self.status_line()
        screen.message(self.stdscr, self.banner if self.banner else "", 2)
        screen.message(self.stdscr, "Enter a FoxBASE+ command", 1)

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

    def rec_info(self):
        db = self.current_dbf
        if not db:
            return ""
        if not db.record_count:
            return "Rec: None"
        if self.eof:
            return f"Rec: EOF/{db.record_count}"
        return f"Rec: {self.current_record + 1}/{db.record_count}"

    def status_line(self, mode=None):
        screen.status_bar(self.stdscr, mode or self.mode_line,
                          self.current_dbf.filename if self.current_dbf else "",
                          self.rec_info(), "Ins" if self.insert_mode else "")

    # ------------------------------------------------------------ keys
    def key(self, ch):
        if self.menubar.active:
            action = self.menubar.key(ch)
            if action:
                self.banner = ""
                action()
            return
        if ch == MENU_KEY:
            self.menubar.open()
            return
        if isinstance(ch, int) and ch >= widgets.ALT_BASE:
            letter = chr(ch - widgets.ALT_BASE).upper()
            for i, (name, _) in enumerate(self.menubar.menus):
                if name[0] == letter:
                    self.menubar.open(i)
                    return
            return
        if ch == curses.KEY_F1:
            self.banner = ""
            self.help("")
            return
        if ch == curses.KEY_IC:
            self.insert_mode = not self.insert_mode
            return
        if ch in (10, 13, curses.KEY_ENTER) or isinstance(ch, str) or \
                ch in (curses.KEY_F2, curses.KEY_F3, curses.KEY_F4, curses.KEY_F5,
                       curses.KEY_F6, curses.KEY_F7, curses.KEY_F8, curses.KEY_F9,
                       curses.KEY_F10):
            self.banner = ""
        self.command.key(ch)

    # ------------------------------------------------------- tela cheia
    def full_screen(self, func, *args, keep=True):
        """Roda uma tela cheia. keep=True (EDIT, APPEND, HELP): a tela fica
        visível acima do ponto, como no original; keep=False limpa a tela
        (BROWSE, CREATE, MODIFY STRUCTURE, MODIFY COMMAND)."""
        result = func(*args)
        h, _ = self.stdscr.getmaxyx()
        if keep:
            rows = ui.snapshot(range(self.top_row(), h - 4))
            self.console.lines = rows + [""]
        else:
            self.console.lines = [""]
        self.console.col = 0
        self.console.just_returned = True
        return result

    def browse(self):
        self.full_screen(self.browser.run, keep=False)

    def edit_current(self, mode="EDIT"):
        db = self.current_dbf
        if not db.record_count or self.eof:
            # EDIT no fim do arquivo abre o último registro, como no original
            if not db.record_count:
                return
            self.current_record, self.eof = db.record_count - 1, False
        self.full_screen(edit_record, self, self.current_record, mode)

    def append_records(self):
        self.full_screen(append_records, self)

    def append_blank(self):
        db = self.current_dbf
        db.append_blank()
        self.current_record, self.eof, self.bof = db.record_count - 1, False, False

    # -------------------------------------------------------- database
    def _resolve(self, filename, suffix):
        path = Path(filename).expanduser()
        if not path.suffix:
            path = path.with_suffix(suffix)
        if not path.exists():
            parent = path.parent if str(path.parent) else Path(".")
            if parent.is_dir():
                for candidate in parent.iterdir():
                    if candidate.name.lower() == path.name.lower():
                        return candidate.resolve()
        return path.resolve()

    def open_dbf(self, filename):
        path = self._resolve(filename, ".dbf")
        try:
            dbf = DBF(path)
        except FileNotFoundError:
            return False
        except (OSError, DBFError):
            raise CommandError("Not a database file.")
        self.current_dbf = dbf
        self.current_dbf_path = str(path)
        self.current_record = 0
        self.eof = dbf.record_count == 0
        self.bof = False
        self.browser.reset()
        return True

    def close_dbf(self):
        self.current_dbf = None
        self.current_dbf_path = None
        self.current_record = 0
        self.eof = self.bof = False

    def create_dbf(self, filename):
        path = Path(filename).expanduser()
        if not path.suffix:
            path = path.with_suffix(".dbf")
        if path.exists() and settings.on("SAFETY"):
            if not self.console.ask_yn(f"\n{str(path.resolve())} already exists, "
                                       "overwrite it? (Y/N) "):
                return
        dbf, input_now = self.full_screen(create_structure, self, path, keep=False)
        if dbf is None:
            return
        self.open_dbf(str(path))
        if input_now:
            self.full_screen(append_records, self, keep=False)

    def modify_structure(self):
        dbf = self.full_screen(modify_structure, self, keep=False)
        if dbf is not None:
            self.open_dbf(str(dbf.filename))

    # --------------------------------------------------------- programs
    def modify_command(self, filename):
        path = self._resolve(filename, ".prg")
        self.full_screen(edit_program, self, path, keep=False)

    def do_program(self, filename):
        path = self._resolve(filename.strip('"\''), ".prg")
        if not path.exists():
            raise CommandError("File does not exist.")
        runner.compile_and_run(self, path)

    def run_shell(self, command):
        if not command:
            command = os.environ.get("SHELL", "/bin/sh")
        runner.run_in_terminal(self, command, shell=True)

    # ------------------------------------------------------------- misc
    def help(self, topic):
        self.full_screen(show_help, self, topic)

    def quit(self):
        self.running = False
        self.quit_message = "FoxBASE+ normal shutdown."
