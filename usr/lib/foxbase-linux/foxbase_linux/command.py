"""Command Window: interpretador de comandos xBase interativo."""

import curses
import fnmatch
import os
from pathlib import Path

from . import ui
from .expr import Evaluator, ExprError, format_value
from .widgets import LineEdit


HELP_TEXT = """\
Commands (abbreviations of 4+ letters are accepted, e.g. BROW, DISP STRU):
  USE [file]              CLOSE DATABASES        CREATE file
  BROWSE                  EDIT / CHANGE [n]      APPEND [BLANK]
  LIST [ALL] [FOR cond]   DISPLAY [ALL]          DISPLAY STRUCTURE
  GO n | GO TOP | GO BOTTOM | n                  SKIP [n]
  LOCATE FOR cond         CONTINUE
  REPLACE fld WITH expr [, fld WITH expr] [ALL] [FOR cond]
  DELETE [ALL] [FOR cond] RECALL [ALL]           PACK      ZAP
  COUNT [FOR cond]        SUM field [FOR cond]
  ? expr[, expr]          ?? expr                STORE expr TO var  /  var = expr
  MODIFY COMMAND file     DO file                RUN cmd  /  ! cmd
  DIR [mask]              CD [dir]               CLEAR     HELP      QUIT
Keys: F10 menu  F2 Use  F3 Browse  F4 Structure  F5 Run  F6 Command
      F7 Editor  F9 Append  Ctrl-Q Quit"""


def kw(word, keyword):
    """xBase: aceita abreviação de 4+ letras (ou a palavra inteira se menor)."""
    word = word.upper()
    if not word or not keyword.startswith(word):
        return False
    return len(word) >= min(4, len(keyword))


def split_for(text):
    """Separa 'xxx FOR cond' -> ('xxx', 'cond')."""
    upper = text.upper()
    idx = upper.find(" FOR ")
    if upper.startswith("FOR "):
        return "", text[4:].strip()
    if idx >= 0:
        return text[:idx].strip(), text[idx + 5:].strip()
    return text.strip(), None


class CommandWindow:
    def __init__(self, app):
        self.app = app
        self.lines = [
            "FoxBASE+ 2.10  (Linux terminal compatibility environment)",
            "Type HELP for a list of commands, F10 for the menu.",
            "",
        ]
        self.edit = LineEdit()
        self.history = []
        self.history_pos = 0
        self.locate_cond = None
        self.evaluator = Evaluator(app)

    # compatibilidade com código antigo que lia/gravava .input
    @property
    def input(self):
        return self.edit.text

    @input.setter
    def input(self, value):
        self.edit.set(value)

    def write(self, text=""):
        for line in str(text).split("\n"):
            self.lines.append(line.replace("\t", "    "))
        self.lines = self.lines[-2000:]

    # ------------------------------------------------------------- tela
    def draw(self, stdscr):
        h, w = stdscr.getmaxyx()
        top = 2
        out_rows = h - 6  # linhas de saída; input na linha h-3
        inner = w - 4
        start = max(0, len(self.lines) - out_rows)
        for row, line in enumerate(self.lines[start:]):
            ui.put(stdscr, top + row, 2, line[:inner])
        ui.put(stdscr, h - 3, 2, ". ", curses.A_BOLD)
        cx = self.edit.draw(stdscr, h - 3, 4, inner - 2)
        return h - 3, cx

    def key(self, ch):
        if ch in (10, 13, curses.KEY_ENTER):
            self.execute()
            return
        if ch == curses.KEY_UP and self.history:
            self.history_pos = max(0, self.history_pos - 1)
            self.input = self.history[self.history_pos]
            return
        if ch == curses.KEY_DOWN and self.history:
            self.history_pos = min(len(self.history), self.history_pos + 1)
            self.input = (self.history[self.history_pos]
                          if self.history_pos < len(self.history) else "")
            return
        if ch == 27:
            self.input = ""
            return
        self.edit.key(ch)

    # ---------------------------------------------------------- execução
    def execute(self, command=None):
        if command is None:
            command = self.input.strip()
            self.input = ""
            if not command:
                return
            if not self.history or self.history[-1] != command:
                self.history.append(command)
            self.history_pos = len(self.history)
        self.write(". " + command)
        try:
            self.dispatch(command)
        except ExprError as exc:
            self.write(str(exc))
        except Exception as exc:  # nunca derrubar o ambiente
            self.write(f"Error: {exc}")

    def require_db(self):
        if not self.app.current_dbf:
            self.write("No database is in use.")
            return None
        return self.app.current_dbf

    def eval(self, text):
        return self.evaluator.evaluate(text)

    def matches(self, index, cond):
        """Avalia cond no registro index (move o ponteiro temporariamente)."""
        if not cond:
            return True
        saved = self.app.current_record, self.app.eof
        self.app.current_record, self.app.eof = index, False
        try:
            return bool(self.eval(cond))
        finally:
            self.app.current_record, self.app.eof = saved

    def dispatch(self, command):
        app = self.app
        words = command.split()
        verb = words[0].upper()
        rest = command[len(words[0]):].strip()
        rest_up = rest.upper()

        # ---- ? / ??
        if command.startswith("??"):
            values = self.evaluator.evaluate_list(command[2:])
            self.write(" ".join(format_value(v) for v in values))
            return
        if command.startswith("?"):
            values = self.evaluator.evaluate_list(command[1:])
            self.write(" ".join(format_value(v) for v in values))
            return
        if command.startswith("!"):
            app.run_shell(command[1:].strip())
            return

        # ---- número sozinho = GOTO
        if verb.isdigit() and len(words) == 1:
            app.goto(int(verb))
            return

        # ---- var = expr
        if len(words) >= 2 and "=" in command and words[0].replace("_", "").isalnum() \
                and command.split("=", 1)[0].strip().replace("_", "").isalnum():
            name, expr = command.split("=", 1)
            app.memvars[name.strip().upper()] = self.eval(expr)
            return

        if kw(verb, "QUIT"):
            app.quit()
        elif kw(verb, "CLEAR"):
            self.lines = []
            if kw(rest_up, "ALL"):
                app.close_dbf()
                app.memvars.clear()
        elif kw(verb, "HELP"):
            self.write(HELP_TEXT)
        elif kw(verb, "USE"):
            if rest:
                app.open_dbf(rest.strip('"\''))
            else:
                app.close_dbf()
        elif kw(verb, "CLOSE"):
            app.close_dbf()
        elif kw(verb, "CREATE"):
            app.create_dbf(rest.strip('"\'') or None)
        elif kw(verb, "BROWSE"):
            app.browse()
        elif kw(verb, "EDIT") or kw(verb, "CHANGE"):
            if rest.isdigit():
                app.goto(int(rest), quiet=True)
            app.edit_current()
        elif kw(verb, "APPEND"):
            app.append_blank(edit=not kw(rest_up, "BLANK"))
        elif kw(verb, "DISPLAY") or kw(verb, "LIST"):
            self.cmd_list(verb, rest, rest_up)
        elif verb in ("GO", "GOTO") or kw(verb, "GOTO"):
            target = rest_up.replace("RECORD", "").strip()
            if kw(target, "TOP"):
                app.goto(1)
            elif kw(target, "BOTTOM"):
                db = self.require_db()
                if db:
                    app.goto(db.record_count)
            else:
                app.goto(int(self.eval(target)))
        elif kw(verb, "SKIP"):
            app.skip(int(self.eval(rest)) if rest else 1)
        elif kw(verb, "LOCATE"):
            _, cond = split_for(rest)
            if not cond:
                self.write("Syntax: LOCATE FOR condition")
                return
            self.locate_cond = cond
            self.cmd_locate(0)
        elif kw(verb, "CONTINUE"):
            if not self.locate_cond:
                self.write("No LOCATE active.")
            else:
                self.cmd_locate(app.current_record + 1)
        elif kw(verb, "REPLACE"):
            self.cmd_replace(rest)
        elif kw(verb, "DELETE") or kw(verb, "RECALL"):
            self.cmd_delete(kw(verb, "DELETE"), rest, rest_up)
        elif kw(verb, "PACK"):
            app.pack()
        elif verb == "ZAP":
            app.zap()
        elif kw(verb, "COUNT"):
            db = self.require_db()
            if db:
                _, cond = split_for(rest)
                n = sum(1 for i in range(db.record_count) if self.matches(i, cond))
                self.write(f"{n:>10} record(s)")
        elif verb == "SUM" or kw(verb, "SUM"):
            self.cmd_sum(rest)
        elif kw(verb, "STORE"):
            idx = rest_up.rfind(" TO ")
            if idx < 0:
                self.write("Syntax: STORE expr TO var")
                return
            value = self.eval(rest[:idx])
            for name in rest[idx + 4:].split(","):
                app.memvars[name.strip().upper()] = value
            self.write(format_value(value))
        elif kw(verb, "MODIFY"):
            parts = rest.split(None, 1)
            if parts and kw(parts[0], "COMMAND"):
                app.modify_command(parts[1] if len(parts) > 1 else None)
            elif parts and kw(parts[0], "STRUCTURE"):
                self.write("MODIFY STRUCTURE is not supported; use CREATE.")
            else:
                self.write("Syntax: MODIFY COMMAND file")
        elif verb == "DO":
            if not rest:
                self.write("Syntax: DO program")
            else:
                app.do_program(rest)
        elif verb == "RUN" or verb == "!":
            app.run_shell(rest)
        elif verb == "DIR":
            self.cmd_dir(rest)
        elif verb in ("CD", "CHDIR"):
            self.cmd_cd(rest)
        elif kw(verb, "SET"):
            self.write("SET commands are accepted but ignored.")
        else:
            self.write("Unrecognized command verb.")

    # ------------------------------------------------------- comandos
    def _record_line(self, db, index):
        rec = db.records[index]
        values = []
        for field, raw in zip(db.fields, rec["values"]):
            width = max(db.display_width(field), len(field["name"]))
            text = db.display_value(field, raw)
            values.append(text.rjust(width) if field["type"] in ("N", "F")
                          else text.ljust(width))
        mark = "*" if rec["deleted"] else " "
        return (f"{index + 1:>7} {mark}" + " ".join(values)).rstrip()

    def cmd_list(self, verb, rest, rest_up):
        app = self.app
        target, cond = split_for(rest)
        target_up = target.upper()
        if target_up and kw(target_up.split()[0], "STRUCTURE"):
            app.structure()
            return
        if target_up and (kw(target_up.split()[0], "MEMORY")):
            if not app.memvars:
                self.write("No memory variables.")
            for name, value in app.memvars.items():
                self.write(f"{name:<12} {format_value(value)}")
            return
        db = self.require_db()
        if not db:
            return
        all_records = kw(verb, "LIST") or kw(target_up, "ALL") or cond
        header = "Record#  " + " ".join(
            (f["name"].rjust if f["type"] in ("N", "F") else f["name"].ljust)(
                max(db.display_width(f), len(f["name"]))) for f in db.fields)
        if all_records:
            self.write(header)
            for index in range(db.record_count):
                if self.matches(index, cond):
                    self.write(self._record_line(db, index))
            app.eof = True
            app.current_record = max(0, db.record_count - 1)
        else:
            if app.eof or not db.record_count:
                self.write("End of file encountered.")
                return
            self.write(header)
            self.write(self._record_line(db, app.current_record))

    def cmd_locate(self, start):
        db = self.require_db()
        if not db:
            return
        for index in range(start, db.record_count):
            if self.matches(index, self.locate_cond):
                self.app.current_record = index
                self.app.eof = False
                self.write(f"Record = {index + 1:>7}")
                return
        self.app.eof = True
        self.write("End of LOCATE scope.")

    def cmd_replace(self, rest):
        app = self.app
        db = self.require_db()
        if not db:
            return
        body, cond = split_for(rest)
        scope_all = False
        if body.upper().endswith(" ALL"):
            body = body[:-4].strip()
            scope_all = True
        pairs = []
        for part in body.split(","):
            idx = part.upper().find(" WITH ")
            if idx < 0:
                self.write("Syntax: REPLACE field WITH expr")
                return
            name, expr = part[:idx].strip(), part[idx + 6:].strip()
            fi = db.field_index(name)
            if fi < 0:
                self.write(f"Variable not found: {name.upper()}")
                return
            pairs.append((fi, expr))
        if scope_all or cond:
            targets = [i for i in range(db.record_count) if self.matches(i, cond)]
        else:
            if app.eof or not db.record_count:
                self.write("End of file encountered.")
                return
            targets = [app.current_record]
        saved = app.current_record
        for index in targets:
            app.current_record = index
            new = [(fi, db.from_typed(db.fields[fi], self.eval(expr))) for fi, expr in pairs]
            for fi, value in new:
                db.records[index]["values"][fi] = value
        app.current_record = saved
        db.save()
        self.write(f"{len(targets):>10} record(s) replaced")

    def cmd_delete(self, delete, rest, rest_up):
        app = self.app
        db = self.require_db()
        if not db:
            return
        target, cond = split_for(rest)
        if kw(target.upper(), "ALL") or cond:
            count = 0
            for index in range(db.record_count):
                if self.matches(index, cond):
                    db.records[index]["deleted"] = delete
                    count += 1
            db.save()
            self.write(f"{count:>10} record(s) {'deleted' if delete else 'recalled'}")
        elif delete:
            app.delete_current()
        else:
            app.recall_current()

    def cmd_sum(self, rest):
        db = self.require_db()
        if not db:
            return
        body, cond = split_for(rest)
        names = [n.strip() for n in body.split(",") if n.strip()]
        if not names:
            names = [f["name"] for f in db.fields if f["type"] in ("N", "F")]
        totals = []
        for name in names:
            fi = db.field_index(name)
            if fi < 0 or db.fields[fi]["type"] not in ("N", "F"):
                self.write(f"Not a numeric field: {name.upper()}")
                return
            total = 0
            for index in range(db.record_count):
                if self.matches(index, cond):
                    total += db.typed_value(index, fi)
            totals.append((name.upper(), total))
        self.write("  ".join(f"{n}={format_value(t).strip()}" for n, t in totals))

    def cmd_dir(self, mask):
        mask = mask.strip() or "*.dbf"
        names = sorted(n for n in os.listdir(".")
                       if fnmatch.fnmatch(n.lower(), mask.lower()))
        if mask.lower() == "*.dbf":
            self.write("Database Files    # Records    Last Update     Size")
            from .dbf import DBF, DBFError
            for name in names:
                try:
                    db = DBF(name)
                    stat = Path(name).stat()
                    import time
                    when = time.strftime("%d/%m/%Y", time.localtime(stat.st_mtime))
                    self.write(f"{name:<16} {db.record_count:>10}    {when:<14} {stat.st_size:>6}")
                except (OSError, DBFError):
                    self.write(f"{name:<16}  (invalid)")
        else:
            for name in names:
                suffix = "/" if os.path.isdir(name) else ""
                self.write(name + suffix)
        self.write(f"{len(names)} file(s)   in {os.getcwd()}")

    def cmd_cd(self, path):
        if not path:
            self.write(os.getcwd())
            return
        try:
            os.chdir(os.path.expanduser(path.strip('"\'')))
            self.write(os.getcwd())
        except OSError as exc:
            self.write(f"Error: {exc}")
