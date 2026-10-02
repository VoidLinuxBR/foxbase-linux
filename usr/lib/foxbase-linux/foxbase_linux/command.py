"""Interpretador da linha de comandos (ponto), reproduzindo o FoxBASE+ 2.10:
mensagens, formatos de LIST/DISPLAY/STRUCTURE/MEMORY/STATUS, DIR e TALK."""

import curses
import fnmatch
import os
import re
import shutil

from . import settings
from .dbf import DBF, DBFError
from .expr import Evaluator, ExprError, Num, format_value, type_letter
from .widgets import LineEdit

TYPE_NAMES = {"C": "Character", "N": "Numeric", "F": "Float", "D": "Date",
              "L": "Logical", "M": "Memo"}

# teclas de função do original (texto digitado + ';' = Enter)
FUNCTION_KEYS = {
    curses.KEY_F2: "central",
    curses.KEY_F3: "list",
    curses.KEY_F4: "dir",
    curses.KEY_F5: "display structure",
    curses.KEY_F6: "display status",
    curses.KEY_F7: "display memory",
    curses.KEY_F8: "display",
    curses.KEY_F9: "append",
    curses.KEY_F10: "edit",
}
FKEY_NAMES = {curses.KEY_F2: "F2", curses.KEY_F3: "F3", curses.KEY_F4: "F4",
              curses.KEY_F5: "F5", curses.KEY_F6: "F6", curses.KEY_F7: "F7",
              curses.KEY_F8: "F8", curses.KEY_F9: "F9", curses.KEY_F10: "F10"}

MAX_VARS = 256
MEMORY_BYTES = 6000


class CommandError(Exception):
    """Erro com a mensagem exata do original."""


def kw(word, keyword):
    """xBase: aceita abreviação de 4+ letras (ou a palavra inteira se menor)."""
    word = word.upper()
    if not word or not keyword.startswith(word):
        return False
    return len(word) >= min(4, len(keyword))


def split_outside_quotes(text, pattern):
    """Encontra pattern (regex) fora de aspas; retorna lista de (pos, match)."""
    found = []
    quote = None
    i = 0
    regex = re.compile(pattern, re.IGNORECASE)
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"[":
            quote = "]" if ch == "[" else ch
            i += 1
            continue
        match = regex.match(text, i)
        if match and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            found.append((i, match))
            i = match.end()
            continue
        i += 1
    return found


def parse_clauses(text):
    """Separa escopo/FOR/WHILE/OFF do resto (lista de campos ou expressão).

    Retorna dict: scope (None, 'ALL', 'REST', ('NEXT', n), ('RECORD', n)),
    for_, while_, off, rest.
    """
    result = {"scope": None, "for_": None, "while_": None, "off": False, "rest": ""}
    marks = split_outside_quotes(
        text, r"(ALL|REST|NEXT|RECORD|FOR|WHILE|OFF)(?=\s|$)")
    if not marks:
        result["rest"] = text.strip()
        return result
    pieces = []
    prev_end = 0
    rest_parts = []
    for i, (pos, match) in enumerate(marks):
        rest_parts.append(text[prev_end:pos])
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        pieces.append((match.group(1).upper(), text[match.end():end]))
        prev_end = end
    rest_parts.insert(0, "")
    for word, arg in pieces:
        if word in ("FOR", "WHILE"):
            if not arg.strip():
                raise CommandError("For/while need logical expressions.")
            result["for_" if word == "FOR" else "while_"] = arg.strip()
            continue
        if word in ("NEXT", "RECORD"):
            parts = arg.strip().split(None, 1)
            if not parts or not parts[0].isdigit():
                raise CommandError("Syntax error.")
            result["scope"] = (word, int(parts[0]))
            rest_parts.append(parts[1] if len(parts) > 1 else "")
            continue
        if word in ("ALL", "REST"):
            result["scope"] = word
        elif word == "OFF":
            result["off"] = True
        rest_parts.append(arg)
    result["rest"] = " ".join(p.strip() for p in rest_parts if p.strip())
    return result


class CommandWindow:
    def __init__(self, app):
        self.app = app
        self.console = app.console
        self.edit = LineEdit()
        self.history = []
        self.history_pos = 0
        self.locate = None  # (cond, while, last index)
        self.evaluator = Evaluator(app)

    # ------------------------------------------------------- compat/saída
    def write(self, text=""):
        self.console.write(text)

    def out(self, text):
        self.console.out(text)

    def msg(self, text):
        self.console.println(text)

    def talk(self, text):
        if settings.on("TALK"):
            self.console.println(text)

    @property
    def input(self):
        return self.edit.text

    @input.setter
    def input(self, value):
        self.edit.set(value)

    # ----------------------------------------------------------- teclado
    def key(self, ch):
        if ch in (10, 13, curses.KEY_ENTER):
            command = self.edit.text
            self.edit.set("")
            self.submit(command)
            return
        if ch in FUNCTION_KEYS:
            self.edit.set("")
            self.submit(FUNCTION_KEYS[ch])
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

    def submit(self, command):
        """Comando digitado: fica na linha do ponto, executa, novo ponto."""
        self.out(command)
        self.console.col = 0
        if command.strip():
            if not self.history or self.history[-1] != command:
                self.history.append(command)
                self.history = self.history[-settings.state["HISTORY_N"]:]
            self.history_pos = len(self.history)
            self.execute(command, echo=False)
        if self.app.running:
            self.console.prompt()

    def execute(self, command, echo=True):
        """Executa um comando. echo=True mostra '. comando' (menus, F-keys)."""
        if echo:
            self.out(command)
            self.console.col = 0
        command = command.strip()
        if command.endswith(";"):
            command = command[:-1].rstrip()
        if not command or command.startswith("*") or command.upper().startswith("NOTE"):
            return
        try:
            self.dispatch(command)
        except (CommandError, ExprError) as exc:
            self.msg(str(exc))
        except DBFError as exc:
            self.msg(str(exc))
        finally:
            self.console.page_lines = None

    # --------------------------------------------------------- utilidades
    def eval(self, text):
        return self.evaluator.evaluate(text)

    def require_db(self):
        """Sem banco aberto: 'No database in USE.  Enter file name: '."""
        if self.app.current_dbf:
            return self.app.current_dbf
        name = self.console.read_line("\nNo database in USE.  Enter file name: ")
        if not name or not name.strip():
            raise CommandError("No database is in USE.")
        if not self.app.open_dbf(name.strip()):
            raise CommandError("File does not exist.")
        return self.app.current_dbf

    def cond(self, text):
        value = self.eval(text)
        if not isinstance(value, bool):
            raise CommandError("For/while need logical expressions.")
        return value

    def records(self, clauses, default_all):
        """Percorre os registros do escopo movendo o ponteiro (como o original)."""
        app = self.app
        db = app.current_dbf
        scope = clauses["scope"]
        if scope is None and (clauses["for_"] or default_all):
            scope = "ALL" if not clauses["while_"] else "REST"
        if scope is None and clauses["while_"]:
            scope = "REST"
        if scope == "ALL":
            indexes = range(0, db.record_count)
        elif scope == "REST":
            indexes = range(app.current_record if not app.eof else db.record_count,
                            db.record_count)
        elif isinstance(scope, tuple) and scope[0] == "NEXT":
            start = app.current_record if not app.eof else db.record_count
            indexes = range(start, min(db.record_count, start + scope[1]))
        elif isinstance(scope, tuple) and scope[0] == "RECORD":
            if not 1 <= scope[1] <= db.record_count:
                raise CommandError("Record is out of range.")
            indexes = [scope[1] - 1]
        else:  # registro atual
            if app.eof or not db.record_count:
                return
            indexes = [app.current_record]

        last = None
        for index in indexes:
            app.current_record, app.eof, app.bof = index, False, False
            if settings.on("DELETED") and db.records[index]["deleted"]:
                continue
            if clauses["while_"] and not self.cond(clauses["while_"]):
                last = index
                break
            if clauses["for_"] and not self.cond(clauses["for_"]):
                continue
            yield index
        else:
            if scope in ("ALL", "REST") or (isinstance(scope, tuple) and scope[0] == "NEXT"
                                             and indexes and indexes[-1] == db.record_count - 1):
                app.current_record = max(0, db.record_count - 1)
                app.eof = True
                return
        if last is not None:
            app.current_record = last

    # ---------------------------------------------------------- dispatch
    def dispatch(self, command):
        app = self.app
        words = command.split()
        verb = words[0].upper()
        rest = command[len(words[0]):].strip()
        rest_up = rest.upper()

        if command.startswith("??"):
            values = self.print_values(command[2:])
            self.out(values)
            return
        if command.startswith("?"):
            text = command[1:]
            self.evaluator.check(text)
            self.out("\n")
            self.out(self.print_values(text))
            return
        if command.startswith("!"):
            app.run_shell(command[1:].strip())
            return
        if verb.isdigit() and len(words) == 1:
            self.go(int(verb))
            return

        # var = expr
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)(.*)$", command)
        if match and not kw(match.group(1), "REPLACE"):
            self.assign([match.group(1)], match.group(2))
            return

        if kw(verb, "QUIT"):
            app.quit()
        elif kw(verb, "CLEAR"):
            if kw(rest_up, "ALL"):
                app.close_dbf()
                app.memvars.clear()
            elif kw(rest_up, "MEMORY"):
                app.memvars.clear()
            else:
                self.console.clear()
        elif kw(verb, "HELP"):
            app.help(rest)
        elif verb in ("ASSIST", "CENTRAL"):
            raise CommandError("File does not exist.")
        elif kw(verb, "USE"):
            if rest:
                if not app.open_dbf(rest.split()[0].strip('"\'')):
                    raise CommandError("File does not exist.")
            else:
                app.close_dbf()
        elif kw(verb, "CLOSE"):
            app.close_dbf()
        elif kw(verb, "CREATE"):
            name = rest.strip('"\'')
            if not name:
                name = self.console.read_line("\nEnter the name of the new file: ")
                if not name:
                    return
            app.create_dbf(name.strip())
        elif kw(verb, "BROWSE"):
            self.require_db()
            app.browse()
        elif kw(verb, "EDIT") or kw(verb, "CHANGE"):
            self.require_db()
            if rest.isdigit():
                self.go(int(rest))
            app.edit_current("CHANGE" if kw(verb, "CHANGE") else "EDIT")
        elif kw(verb, "APPEND"):
            self.require_db()
            if kw(rest_up, "BLANK"):
                app.append_blank()
            else:
                app.append_records()
        elif kw(verb, "INSERT"):
            self.require_db()
            app.append_records()
        elif kw(verb, "DISPLAY") or kw(verb, "LIST"):
            self.cmd_list(kw(verb, "LIST"), rest)
        elif verb in ("GO", "GOTO") or kw(verb, "GOTO"):
            self.require_db()
            target = rest_up.replace("RECORD", "").strip()
            if kw(target, "TOP"):
                self.go_top()
            elif kw(target, "BOTTOM"):
                self.go_bottom()
            elif target:
                self.go(int(float(self.eval(target))))
            else:
                raise CommandError("Syntax error.")
        elif kw(verb, "SKIP"):
            self.require_db()
            self.skip(int(float(self.eval(rest))) if rest else 1)
        elif kw(verb, "LOCATE"):
            self.require_db()
            clauses = parse_clauses(rest)
            if not clauses["for_"]:
                raise CommandError("Syntax error.")
            self.locate = clauses
            self.cmd_locate(start=True)
        elif kw(verb, "CONTINUE"):
            self.require_db()
            if not self.locate:
                raise CommandError("No locate active.")
            self.cmd_locate(start=False)
        elif kw(verb, "REPLACE"):
            self.cmd_replace(rest)
        elif kw(verb, "DELETE") or kw(verb, "RECALL"):
            self.cmd_delete(kw(verb, "DELETE"), rest)
        elif kw(verb, "PACK"):
            db = self.require_db()
            db.pack()
            self.talk(f"{db.record_count:7d} records copied")
            app.current_record, app.eof = 0, db.record_count == 0
        elif verb == "ZAP":
            db = self.require_db()
            if settings.on("SAFETY") and not self.console.ask_yn(
                    f"\nZap {str(db.filename)}? (Y/N) "):
                return
            db.zap()
            app.current_record, app.eof = 0, True
        elif kw(verb, "COUNT"):
            self.cmd_count(rest)
        elif kw(verb, "SUM") or kw(verb, "AVERAGE"):
            self.cmd_sum(rest, average=kw(verb, "AVERAGE"))
        elif kw(verb, "STORE"):
            idx = rest_up.rfind(" TO ")
            if idx < 0:
                raise CommandError("Syntax error.")
            self.assign([n.strip() for n in rest[idx + 4:].split(",")], rest[:idx])
        elif kw(verb, "RELEASE"):
            for name in re.split(r"[,\s]+", rest_up.replace("ALL", "")):
                app.memvars.pop(name, None)
            if kw(rest_up, "ALL"):
                app.memvars.clear()
        elif kw(verb, "MODIFY"):
            parts = rest.split(None, 1)
            if parts and kw(parts[0], "STRUCTURE"):
                self.require_db()
                app.modify_structure()
            elif parts and kw(parts[0], "COMMAND"):
                name = parts[1].strip() if len(parts) > 1 else ""
                if not name:
                    name = self.console.read_line("\nEnter file name: ")
                    if not name:
                        return
                app.modify_command(name.strip())
            else:
                raise CommandError("Unrecognized phrase/keyword in command.")
        elif verb == "DO":
            if not rest:
                raise CommandError("Syntax error.")
            app.do_program(rest.split()[0])
        elif verb == "RUN":
            app.run_shell(rest)
        elif verb == "DIR":
            self.cmd_dir(rest)
        elif kw(verb, "SET"):
            self.cmd_set(rest)
        elif kw(verb, "WAIT"):
            text = rest.strip("'\"") if rest else "Press any key to continue..."
            self.console.wait(text)
        else:
            raise CommandError("Unrecognized command verb.")

    # ------------------------------------------------------------ valores
    def print_values(self, text):
        values = self.evaluator.evaluate_list(text)
        return " ".join(format_value(v) for v in values)

    def assign(self, names, expr):
        value = self.eval(expr)
        if isinstance(value, Num):
            value = Num(float(value), 10, value.dec)
        for name in names:
            name = name.strip().upper()[:10]
            if not name:
                raise CommandError("Syntax error.")
            if name not in self.app.memvars and len(self.app.memvars) >= MAX_VARS:
                raise CommandError("Too many memory variables.")
            self.app.memvars[name] = value
        shown = self.eval(expr)
        self.talk(format_value(shown))

    # ----------------------------------------------------------- ponteiro
    def go(self, number):
        db = self.require_db()
        if not 1 <= number <= db.record_count:
            raise CommandError("Record is out of range.")
        self.app.current_record, self.app.eof, self.app.bof = number - 1, False, False

    def go_top(self):
        db = self.app.current_dbf
        self.app.current_record, self.app.bof = 0, False
        self.app.eof = db.record_count == 0
        if settings.on("DELETED"):
            for i in range(db.record_count):
                if not db.records[i]["deleted"]:
                    self.app.current_record = i
                    return
            self.app.eof = True

    def go_bottom(self):
        db = self.app.current_dbf
        self.app.current_record = max(0, db.record_count - 1)
        self.app.eof, self.app.bof = db.record_count == 0, False

    def skip(self, count):
        app = self.app
        db = app.current_dbf
        if app.eof and count > 0:
            raise CommandError("End of file encountered.")
        if app.bof and count < 0:
            raise CommandError("Beginning of file encountered.")
        pos = db.record_count if app.eof else app.current_record
        step = 1 if count > 0 else -1
        for _ in range(abs(count)):
            pos += step
            while 0 <= pos < db.record_count and settings.on("DELETED") \
                    and db.records[pos]["deleted"]:
                pos += step
            if pos >= db.record_count or pos < 0:
                break
        if pos >= db.record_count:
            app.current_record, app.eof, app.bof = max(0, db.record_count - 1), True, False
            self.talk(f"Record No. {db.record_count + 1}")
        elif pos < 0:
            app.current_record, app.eof, app.bof = 0, False, True
            self.talk("Record No. 1")
        else:
            app.current_record, app.eof, app.bof = pos, False, False
            self.talk(f"Record No. {pos + 1}")

    # -------------------------------------------------------- LIST/DISPLAY
    def cmd_list(self, is_list, rest):
        clauses = parse_clauses(rest)
        target = clauses["rest"].upper()
        first = target.split()[0] if target else ""
        if first and kw(first, "STRUCTURE"):
            self.cmd_structure(paged=not is_list)
            return
        if first and kw(first, "MEMORY"):
            self.cmd_memory(paged=not is_list)
            return
        if first and kw(first, "STATUS"):
            self.cmd_status(paged=not is_list)
            return
        if first and kw(first, "FILES"):
            self.cmd_dir(clauses["rest"].split(None, 1)[1] if " " in clauses["rest"] else "*.*")
            return
        db = self.require_db()

        if clauses["rest"]:
            exprs = [e.strip() for e in clauses["rest"].split(",") if e.strip()]
        else:
            exprs = [f["name"] for f in db.fields]
        columns = []
        for expr in exprs:
            fi = db.field_index(expr)
            if fi >= 0:
                field = db.fields[fi]
                width = max(len(field["name"]), db.display_width(field))
                right = field["type"] in ("N", "F")
                columns.append(("field", fi, field["name"], width, right))
            else:
                text = self._sample(db, expr)
                header_text = self._expr_header(expr)
                right = text is not None and text[1]
                width = max(len(header_text), len(text[0]) if text else 0)
                columns.append(("expr", expr, header_text, width, right))

        if not is_list and clauses["scope"] is not None:
            self.console.page_lines = 0
        header = "" if clauses["off"] else "Record#  "
        cells = []
        for kind, ref, name, width, right in columns:
            cells.append(name.rjust(width) if right else name.ljust(width))
        if settings.on("HEADING"):
            self.out("\n" + (header + " ".join(cells)).rstrip())

        for index in self.records(clauses, default_all=is_list):
            record = db.records[index]
            line = "" if clauses["off"] else f"{index + 1:7d} " + ("*" if record["deleted"] else " ")
            values = []
            for kind, ref, name, width, right in columns:
                if kind == "field":
                    field = db.fields[ref]
                    text = db.list_value(field, record["values"][ref])
                    values.append(text.rjust(width) if right else text.ljust(width))
                else:
                    value = self.eval(ref)
                    text = format_value(value)
                    values.append(text.rjust(width) if isinstance(value, Num)
                                  else text.ljust(width))
            self.out("\n" + line + " ".join(values))
        self.out("\n")

    def _sample(self, db, expr):
        """Avalia a expressão num registro para saber a largura da coluna."""
        app = self.app
        saved = (app.current_record, app.eof)
        if app.eof and db.record_count:
            app.current_record, app.eof = 0, False
        try:
            value = self.eval(expr)
            return format_value(value), isinstance(value, Num)
        finally:
            app.current_record, app.eof = saved

    @staticmethod
    def _expr_header(expr):
        """Cabeçalho da coluna: expressão em maiúsculas fora das aspas, com "."""
        out, quote = "", None
        for ch in expr:
            if quote:
                out += '"' if ch == quote else ch
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
                out += '"'
            else:
                out += ch.upper()
        return out

    def cmd_structure(self, paged=False):
        db = self.require_db()
        if paged:
            self.console.page_lines = 0
        when = settings.fmt_date(db.last_update) if db.last_update else settings.blank_date()
        self.msg(f"Structure for database: {str(db.filename)}")
        self.msg(f"Number of data records:{db.record_count:8d}")
        self.msg(f"Date of last update   : {when}")
        self.msg("Field  Field Name  Type       Width    Dec")
        for i, field in enumerate(db.fields, 1):
            line = (f"{i:5d}  {field['name']:<10}  "
                    f"{TYPE_NAMES.get(field['type'], '<unknown>'):<10}{field['length']:6d}")
            if field["type"] in ("N", "F") and field["decimals"]:
                line += f"{field['decimals']:7d}"
            self.msg(line)
        self.msg(f"** Total **                   {db.record_length:5d}")
        self.out("\n")

    def cmd_memory(self, paged=False):
        if paged:
            self.console.page_lines = 0
        used = 0
        for name, value in self.app.memvars.items():
            kind = type_letter(value)
            if kind == "N":
                text = f"N {format_value(value).strip():>11}  ({float(value):19.8f})"
                used += 7
            elif kind == "C":
                text = f'C  "{value}"'
                used += len(value)
            elif kind == "D":
                text = f"D  {format_value(value)}"
                used += 7
            else:
                text = f"L  {format_value(value)}"
                used += 1
            self.msg(f"{name:<12}Pub   {text}")
        count = len(self.app.memvars)
        self.msg(f"{count:5d} variables defined,    {used:5d} bytes used")
        self.msg(f"{MAX_VARS - count:5d} variables available,  "
                 f"{MEMORY_BYTES - used:5d} bytes available")
        self.out("\n")

    def cmd_status(self, paged=True):
        app = self.app
        self.console.page_lines = 0 if paged else None
        self.out("\n")
        self.msg("Processor is INTEL 80386")
        if app.current_dbf:
            db = app.current_dbf
            self.msg("Currently Selected Database:")
            self.msg(f"Select area:  1, Database in Use: {str(db.filename)}    "
                     f"Alias: {db.filename.stem.upper()}")
        self.out("\n")
        self.msg("File search path:")
        self.msg(f"Default disk drive: {os.getcwd()}")
        self.msg("Print file/device:  PRN:")
        self.msg("Work area =   1")
        self.msg(f"Margin    = {settings.state['MARGIN']:3d}")
        self.msg(f"Decimals  = {settings.state['DECIMALS']:3d}")
        self.msg(f"Memowidth = {settings.state['MEMOWIDTH']:3d}")
        self.msg(f"Typeahead = {settings.state['TYPEAHEAD']:3d}")
        self.msg(f"History   = {settings.state['HISTORY_N']:3d}")
        self.out("\n")
        self.msg(f"Date format: {settings.DATE_NAMES[settings.state['DATE']]}")
        self.out("\n")
        names = [name for name, _ in settings.SWITCHES if name != "DEVICE"]
        names.insert(names.index("DOHISTORY"), "DEVICE")
        rows = (len(names) + 3) // 4
        for r in range(rows):
            parts = []
            for c in range(4):
                i = c * rows + r
                if i >= len(names):
                    continue
                name = names[i]
                value = settings.state[name]
                shown = value if isinstance(value, str) else ("on" if value else "off")
                parts.append(f"{name.capitalize():<10} - {shown:<4}")
            self.msg("   ".join(parts).rstrip())
        self.out("\n\n")
        self.msg("Programmable function keys:")
        for key, text in FUNCTION_KEYS.items():
            self.msg(f"{FKEY_NAMES[key]} - {text};")
        self.out("\n")

    # ------------------------------------------------------------ busca
    def cmd_locate(self, start):
        app = self.app
        db = app.current_dbf
        clauses = dict(self.locate)
        if start:
            clauses["scope"] = clauses["scope"] or "ALL"
            iterator = self.records(clauses, default_all=True)
        else:
            if app.eof:
                raise CommandError("End of Locate scope.")
            app.current_record += 1
            if app.current_record >= db.record_count:
                app.current_record, app.eof = max(0, db.record_count - 1), True
                app.found = False
                self.msg("End of Locate scope.")
                return
            clauses["scope"] = "REST"
            iterator = self.records(clauses, default_all=True)
        for index in iterator:
            app.found = True
            self.talk(f"Record = {index + 1}")
            return
        app.found = False
        app.current_record, app.eof = max(0, db.record_count - 1), True
        self.msg("End of Locate scope.")

    # ----------------------------------------------------------- alteração
    def cmd_replace(self, rest):
        db = self.require_db()
        clauses = parse_clauses(rest)
        pairs = []
        for part in self._split_commas(clauses["rest"]):
            idx = part.upper().find(" WITH ")
            if idx < 0:
                raise CommandError("Syntax error.")
            name, expr = part[:idx].strip(), part[idx + 6:].strip()
            fi = db.field_index(name)
            if fi < 0:
                raise CommandError("Variable not found.")
            pairs.append((fi, expr))
        count = 0
        for index in self.records(clauses, default_all=False):
            new = []
            for fi, expr in pairs:
                field = db.fields[fi]
                value = self.eval(expr)
                if type_letter(value) != {"F": "N", "M": "C"}.get(field["type"], field["type"]):
                    raise CommandError("Data type mismatch.")
                if field["type"] == "M":
                    new.append((fi, db.write_memo(value.rstrip())))
                else:
                    new.append((fi, db.from_typed(field, format_value(value).strip()
                                                  if isinstance(value, Num) else value)))
            for fi, raw in new:
                db.records[index]["values"][fi] = raw
            count += 1
        db.save()
        self.talk(f"{count:7d} replacements")

    @staticmethod
    def _split_commas(text):
        parts, depth, quote, cur = [], 0, None, ""
        for ch in text:
            if quote:
                cur += ch
                if ch == quote:
                    quote = None
                continue
            if ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
                continue
            cur += ch
        if cur.strip():
            parts.append(cur)
        return parts

    def cmd_delete(self, delete, rest):
        db = self.require_db()
        clauses = parse_clauses(rest)
        if clauses["rest"].upper().startswith("FILE"):
            name = clauses["rest"].split(None, 1)[1] if " " in clauses["rest"] else ""
            try:
                os.remove(name.strip())
                self.talk("File has been deleted.")
            except OSError:
                raise CommandError("File does not exist.")
            return
        count = 0
        for index in self.records(clauses, default_all=False):
            if db.records[index]["deleted"] != delete:
                db.records[index]["deleted"] = delete
            count += 1
        db.save()
        self.talk(f"{count:7d} records {'deleted' if delete else 'recalled'}")

    # ------------------------------------------------------------ contas
    def cmd_count(self, rest):
        self.require_db()
        clauses = parse_clauses(rest)
        count = sum(1 for _ in self.records(clauses, default_all=True))
        self.talk(f"{count:7d} records")

    def cmd_sum(self, rest, average=False):
        db = self.require_db()
        clauses = parse_clauses(rest)
        if clauses["rest"]:
            exprs = [e.strip() for e in self._split_commas(clauses["rest"])]
        else:
            exprs = [f["name"] for f in db.fields if f["type"] in ("N", "F")]
        specs = []
        for expr in exprs:
            fi = db.field_index(expr)
            if fi >= 0:
                field = db.fields[fi]
                if field["type"] not in ("N", "F"):
                    raise CommandError("Not a numeric expression.")
                specs.append((expr.upper(), field["length"], field["decimals"]))
            else:
                specs.append((expr.upper(), 10, settings.state["DECIMALS"]))
        totals = [0.0] * len(exprs)
        count = 0
        for _ in self.records(clauses, default_all=True):
            for i, expr in enumerate(exprs):
                value = self.eval(expr)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise CommandError("Not a numeric expression.")
                totals[i] += float(value)
            count += 1
        word = "averaged." if average else "summed."
        self.talk(f"{count:7d} records {word}")
        if not settings.on("TALK"):
            return
        names, values = [], []
        for (name, width, dec), total in zip(specs, totals):
            if average:
                dec = dec or settings.state["DECIMALS"]
                total = total / count if count else 0.0
                width = width if dec else width + 3
            else:
                width += 3
            text = f"{total:.{dec}f}" if dec else str(int(round(total)))
            names.append(name.rjust(width))
            values.append(text.rjust(width))
        self.msg(" ".join(names))
        self.msg(" ".join(values))

    # --------------------------------------------------------------- DIR
    def cmd_dir(self, mask):
        mask = mask.strip() or "*.DBF"
        names = sorted(n for n in os.listdir(".")
                       if fnmatch.fnmatch(n.upper(), mask.upper()) and os.path.isfile(n))
        total = 0
        if mask.upper() == "*.DBF":
            self.msg("Database Files    # Records    Last Update    Size")
            for name in names:
                size = os.path.getsize(name)
                total += size
                try:
                    db = DBF(name)
                    when = settings.fmt_date(db.last_update) if db.last_update \
                        else settings.blank_date()
                    self.msg(f"{name.upper():<12}{db.record_count:15d}    {when:<8}{size:11d}")
                except (OSError, DBFError):
                    self.msg(f"{name.upper():<12}{'':15}    {'':8}{size:11d}")
        else:
            line = ""
            for name in names:
                total += os.path.getsize(name)
                line += f"{name:<16}"
                if len(line) >= 80:
                    self.msg(line.rstrip())
                    line = ""
            if line:
                self.msg(line.rstrip())
        self.out("\n")
        self.msg(f"{total:7d} bytes in {len(names)} files.")
        free = shutil.disk_usage(".").free
        self.msg(f"{free:7d} bytes remaining on drive.")
        self.out("\n")

    # --------------------------------------------------------------- SET
    def cmd_set(self, rest):
        words = rest.split()
        if not words:
            self.cmd_status(paged=True)
            return
        name = words[0].upper()
        value = " ".join(words[1:])
        value_up = value.upper()
        for switch, _ in settings.SWITCHES:
            if kw(name, switch) and switch != "DEVICE":
                if value_up in ("ON", "OFF"):
                    settings.state[switch] = value_up == "ON"
                    return
                if not value_up and switch in ("CLEAR",):
                    return
                raise CommandError("Syntax error.")
        if kw(name, "DATE"):
            fmt = value_up.replace("TO", "").strip()
            for key in settings.DATE_FORMATS:
                if key.startswith(fmt) and fmt:
                    settings.state["DATE"] = key
                    return
            raise CommandError("Syntax error.")
        if kw(name, "DECIMALS"):
            settings.state["DECIMALS"] = int(value_up.replace("TO", "").strip() or 0)
            return
        if kw(name, "MARGIN"):
            settings.state["MARGIN"] = int(value_up.replace("TO", "").strip() or 0)
            return
        if kw(name, "MEMOWIDTH"):
            settings.state["MEMOWIDTH"] = int(value_up.replace("TO", "").strip() or 50)
            return
        if kw(name, "DEFAULT") or kw(name, "PATH"):
            path = value.split(None, 1)[1] if value_up.startswith("TO") and " " in value \
                else value.replace("TO", "", 1).strip()
            if path:
                try:
                    os.chdir(os.path.expanduser(path.strip('"\'')))
                except OSError:
                    raise CommandError("File does not exist.")
            return
        if kw(name, "DEVICE"):
            settings.state["DEVICE"] = "prnt" if "PRIN" in value_up else "scrn"
            return
        # demais SET são aceitos como no original, sem efeito aqui
